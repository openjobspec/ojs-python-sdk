"""Benchmark tests for OJS Python SDK using pytest-benchmark.

Run with: pytest tests/test_benchmarks.py --benchmark-only
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from ojs.errors import OJSErrorDetail, raise_for_error
from ojs.job import Job, JobContext, JobRequest, JobState, UniquePolicy
from ojs.middleware import ExecutionMiddlewareChain
from ojs.retry import RetryPolicy


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

MINIMAL_JOB_DICT: dict[str, Any] = {
    "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "type": "email.send",
    "state": "available",
    "queue": "default",
    "args": [{"to": "user@example.com"}],
    "attempt": 0,
    "created_at": "2024-01-15T10:30:00Z",
}

FULL_JOB_DICT: dict[str, Any] = {
    "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "type": "email.send",
    "state": "active",
    "queue": "email",
    "args": [{"to": "user@example.com", "subject": "Welcome!"}],
    "priority": 10,
    "attempt": 2,
    "max_attempts": 5,
    "timeout_ms": 30000,
    "tags": ["onboarding", "email", "priority"],
    "meta": {"campaign_id": "123", "source": "api"},
    "retry": {
        "max_attempts": 5,
        "initial_interval": "PT2S",
        "backoff_coefficient": 2.0,
        "max_interval": "PT5M",
        "jitter": True,
        "non_retryable_errors": ["invalid_input"],
    },
    "unique": {
        "key": ["type", "queue", "args"],
        "period": "PT5M",
        "states": ["available", "active"],
        "on_conflict": "reject",
    },
    "created_at": "2024-01-15T10:30:00Z",
    "scheduled_at": "2024-01-15T11:00:00Z",
}

LARGE_JOB_DICT: dict[str, Any] = {
    "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "type": "data.pipeline.transform",
    "state": "active",
    "queue": "data-pipeline",
    "args": [
        {
            "input_path": "/data/raw/2024/01/events.parquet",
            "output_path": "/data/processed/2024/01/events.parquet",
            "transforms": ["deduplicate", "normalize", "aggregate"],
            "config": {
                "partition_by": ["date", "region"],
                "compression": "zstd",
                "row_limit": 1_000_000,
            },
            "filters": {f"field_{i}": f"value_{i}" for i in range(20)},
        }
    ],
    "priority": 100,
    "attempt": 1,
    "max_attempts": 3,
    "timeout_ms": 600000,
    "tags": [f"tag-{i}" for i in range(15)],
    "meta": {f"key_{i}": f"value_{i}" for i in range(10)},
    "created_at": "2024-01-15T10:30:00Z",
    "scheduled_at": "2024-01-15T11:00:00Z",
}

ERROR_RESPONSE_DICT: dict[str, Any] = {
    "error": {
        "code": "validation_failed",
        "message": "Job type 'email.send' requires a valid recipient",
        "retryable": False,
        "details": {"field": "args.to", "constraint": "email_format"},
        "request_id": "req-abc-123",
    }
}


# ---------------------------------------------------------------------------
# Job serialization benchmarks
# ---------------------------------------------------------------------------


class TestJobSerialization:
    """Benchmark JobRequest.to_dict() for various payload sizes."""

    def test_serialize_minimal(self, benchmark: Any) -> None:
        req = JobRequest(type="email.send", args=["user@example.com"])
        benchmark(req.to_dict)

    def test_serialize_medium(self, benchmark: Any) -> None:
        req = JobRequest(
            type="email.send",
            args=[{"to": "user@example.com", "subject": "Welcome!"}],
            queue="email",
            priority=10,
            tags=["onboarding", "email"],
        )
        benchmark(req.to_dict)

    def test_serialize_full(self, benchmark: Any) -> None:
        req = JobRequest(
            type="email.send",
            args=[{"to": "user@example.com", "subject": "Welcome!"}],
            queue="email",
            priority=10,
            timeout_ms=30000,
            tags=["onboarding", "email", "priority"],
            retry=RetryPolicy(
                max_attempts=5,
                initial_interval="PT2S",
                non_retryable_errors=["invalid_input"],
            ),
            unique=UniquePolicy(
                keys=["type", "queue", "args"],
                period="PT5M",
                on_conflict="reject",
            ),
        )
        benchmark(req.to_dict)

    def test_serialize_to_json_minimal(self, benchmark: Any) -> None:
        req = JobRequest(type="email.send", args=["user@example.com"])

        def serialize() -> str:
            return json.dumps(req.to_dict())

        benchmark(serialize)

    def test_serialize_to_json_full(self, benchmark: Any) -> None:
        req = JobRequest(
            type="email.send",
            args=[{"to": "user@example.com", "subject": "Welcome!"}],
            queue="email",
            priority=10,
            tags=["onboarding"],
            retry=RetryPolicy(max_attempts=5),
        )

        def serialize() -> str:
            return json.dumps(req.to_dict())

        benchmark(serialize)


# ---------------------------------------------------------------------------
# Job deserialization benchmarks
# ---------------------------------------------------------------------------


class TestJobDeserialization:
    """Benchmark Job.from_dict() for various payload sizes."""

    def test_deserialize_minimal(self, benchmark: Any) -> None:
        benchmark(Job.from_dict, MINIMAL_JOB_DICT)

    def test_deserialize_full(self, benchmark: Any) -> None:
        benchmark(Job.from_dict, FULL_JOB_DICT)

    def test_deserialize_large(self, benchmark: Any) -> None:
        benchmark(Job.from_dict, LARGE_JOB_DICT)

    def test_deserialize_from_json_minimal(self, benchmark: Any) -> None:
        data = json.dumps(MINIMAL_JOB_DICT)

        def deserialize() -> Job:
            return Job.from_dict(json.loads(data))

        benchmark(deserialize)

    def test_deserialize_from_json_full(self, benchmark: Any) -> None:
        data = json.dumps(FULL_JOB_DICT)

        def deserialize() -> Job:
            return Job.from_dict(json.loads(data))

        benchmark(deserialize)

    def test_roundtrip_serialize_deserialize(self, benchmark: Any) -> None:
        req = JobRequest(
            type="data.process",
            args=[{"input": "data.csv", "format": "json"}],
            queue="default",
            priority=5,
            tags=["etl"],
        )

        def roundtrip() -> Job:
            d = req.to_dict()
            d.update(
                id="test-roundtrip",
                state="available",
                attempt=0,
                created_at="2024-01-15T10:30:00Z",
            )
            return Job.from_dict(d)

        benchmark(roundtrip)


# ---------------------------------------------------------------------------
# Args encoding benchmarks
# ---------------------------------------------------------------------------


class TestArgsEncoding:
    """Benchmark args encoding as it passes through serialization."""

    def test_args_empty(self, benchmark: Any) -> None:
        req = JobRequest(type="noop", args=[])
        benchmark(req.to_dict)

    def test_args_positional(self, benchmark: Any) -> None:
        req = JobRequest(type="math.add", args=[1, 2, 3, 4, 5])
        benchmark(req.to_dict)

    def test_args_single_dict(self, benchmark: Any) -> None:
        req = JobRequest(
            type="email.send",
            args=[{"to": "user@example.com", "subject": "hello"}],
        )
        benchmark(req.to_dict)

    def test_args_large_dict(self, benchmark: Any) -> None:
        large_args = [{f"key_{i}": f"value_{i}" for i in range(50)}]
        req = JobRequest(type="bulk.process", args=large_args)
        benchmark(req.to_dict)


# ---------------------------------------------------------------------------
# Error parsing benchmarks
# ---------------------------------------------------------------------------


class TestErrorParsing:
    """Benchmark error response parsing."""

    def test_parse_error_detail(self, benchmark: Any) -> None:
        error_data = ERROR_RESPONSE_DICT["error"]

        def parse() -> OJSErrorDetail:
            return OJSErrorDetail(
                code=error_data.get("code", "unknown"),
                message=error_data.get("message", "Unknown error"),
                retryable=error_data.get("retryable", False),
                details=error_data.get("details", {}),
                request_id=error_data.get("request_id"),
            )

        benchmark(parse)

    def test_raise_for_error_validation(self, benchmark: Any) -> None:
        def parse_error() -> None:
            try:
                raise_for_error(422, ERROR_RESPONSE_DICT)
            except Exception:
                pass

        benchmark(parse_error)

    def test_raise_for_error_not_found(self, benchmark: Any) -> None:
        body: dict[str, Any] = {
            "error": {
                "code": "not_found",
                "message": "Job not found",
                "retryable": False,
            }
        }

        def parse_error() -> None:
            try:
                raise_for_error(404, body)
            except Exception:
                pass

        benchmark(parse_error)

    def test_raise_for_error_duplicate(self, benchmark: Any) -> None:
        body: dict[str, Any] = {
            "error": {
                "code": "duplicate",
                "message": "Duplicate job",
                "retryable": False,
            }
        }

        def parse_error() -> None:
            try:
                raise_for_error(409, body)
            except Exception:
                pass

        benchmark(parse_error)


# ---------------------------------------------------------------------------
# Middleware chain benchmarks
# ---------------------------------------------------------------------------


class TestMiddlewareChain:
    """Benchmark execution middleware chains of varying depth."""

    def _run_chain(self, depth: int) -> None:
        chain = ExecutionMiddlewareChain()
        for _ in range(depth):

            async def mw(ctx: JobContext, nxt: Any) -> Any:
                return await nxt()

            chain.add(mw)

        job = Job(id="bench", type="test", state=JobState.AVAILABLE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        asyncio.get_event_loop().run_until_complete(chain.execute(ctx, handler))

    def test_middleware_direct(self, benchmark: Any) -> None:
        """Baseline: handler with no middleware."""
        job = Job(id="bench", type="test", state=JobState.AVAILABLE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        loop = asyncio.new_event_loop()

        def run() -> Any:
            return loop.run_until_complete(handler(ctx))

        benchmark(run)
        loop.close()

    def test_middleware_chain_1(self, benchmark: Any) -> None:
        self._bench_middleware(benchmark, 1)

    def test_middleware_chain_3(self, benchmark: Any) -> None:
        self._bench_middleware(benchmark, 3)

    def test_middleware_chain_5(self, benchmark: Any) -> None:
        self._bench_middleware(benchmark, 5)

    def test_middleware_chain_10(self, benchmark: Any) -> None:
        self._bench_middleware(benchmark, 10)

    def _bench_middleware(self, benchmark: Any, depth: int) -> None:
        chain = ExecutionMiddlewareChain()
        for _ in range(depth):

            async def mw(ctx: JobContext, nxt: Any) -> Any:
                return await nxt()

            chain.add(mw)

        job = Job(id="bench", type="test", state=JobState.AVAILABLE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        loop = asyncio.new_event_loop()

        def run() -> Any:
            return loop.run_until_complete(chain.execute(ctx, handler))

        benchmark(run)
        loop.close()


# ---------------------------------------------------------------------------
# Validation benchmarks
# ---------------------------------------------------------------------------


class TestValidation:
    """Benchmark parameter validation via JobRequest construction and serialization."""

    def test_validate_enqueue_minimal(self, benchmark: Any) -> None:
        def validate() -> dict[str, Any]:
            req = JobRequest(type="email.send", args=[{"to": "user@example.com"}])
            return req.to_dict()

        benchmark(validate)

    def test_validate_enqueue_full(self, benchmark: Any) -> None:
        def validate() -> dict[str, Any]:
            req = JobRequest(
                type="email.send",
                args=[{"to": "user@example.com"}],
                queue="email",
                priority=10,
                timeout_ms=30000,
                tags=["onboarding"],
                retry=RetryPolicy(max_attempts=5),
                unique=UniquePolicy(
                    keys=["type", "queue", "args"],
                    period="PT5M",
                    on_conflict="reject",
                ),
            )
            return req.to_dict()

        benchmark(validate)

    def test_validate_job_state_is_terminal(self, benchmark: Any) -> None:
        states = list(JobState)

        def check_all() -> list[bool]:
            return [s.is_terminal for s in states]

        benchmark(check_all)

    def test_validate_retry_policy_serialization(self, benchmark: Any) -> None:
        policy = RetryPolicy(
            max_attempts=5,
            initial_interval="PT2S",
            backoff_coefficient=2.0,
            max_interval="PT5M",
            jitter=True,
            non_retryable_errors=["invalid_input"],
        )
        benchmark(policy.to_dict)

    def test_validate_retry_policy_deserialization(self, benchmark: Any) -> None:
        data: dict[str, Any] = {
            "max_attempts": 5,
            "initial_interval": "PT2S",
            "backoff_coefficient": 2.0,
            "max_interval": "PT5M",
            "jitter": True,
            "non_retryable_errors": ["invalid_input"],
        }
        benchmark(RetryPolicy.from_dict, data)

    def test_validate_unique_policy_roundtrip(self, benchmark: Any) -> None:
        data: dict[str, Any] = {
            "key": ["type", "queue"],
            "period": "PT5M",
            "states": ["available", "active"],
            "on_conflict": "reject",
        }

        def roundtrip() -> dict[str, Any]:
            policy = UniquePolicy.from_dict(data)
            return policy.to_dict()

        benchmark(roundtrip)


# ---------------------------------------------------------------------------
# Client request building benchmarks
# ---------------------------------------------------------------------------


class TestClientRequestBuilding:
    """Benchmark building request payloads without sending."""

    def test_build_single_enqueue_request(self, benchmark: Any) -> None:
        def build() -> dict[str, Any]:
            req = JobRequest(
                type="email.send",
                args=[{"to": "user@example.com"}],
                queue="email",
                priority=5,
            )
            return req.to_dict()

        benchmark(build)

    def test_build_batch_enqueue_request(self, benchmark: Any) -> None:
        def build() -> list[dict[str, Any]]:
            requests = [
                JobRequest(type="email.send", args=[f"user{i}@example.com"])
                for i in range(10)
            ]
            return [r.to_dict() for r in requests]

        benchmark(build)

    def test_build_batch_enqueue_large(self, benchmark: Any) -> None:
        def build() -> list[dict[str, Any]]:
            requests = [
                JobRequest(
                    type="email.send",
                    args=[{"to": f"user{i}@example.com", "subject": f"Message {i}"}],
                    queue="email",
                    priority=i % 10,
                    tags=["batch", f"group-{i % 5}"],
                )
                for i in range(100)
            ]
            return [r.to_dict() for r in requests]

        benchmark(build)

    def test_build_request_with_retry_and_unique(self, benchmark: Any) -> None:
        def build() -> dict[str, Any]:
            req = JobRequest(
                type="payment.process",
                args=[{"order_id": "ord-123", "amount": 99.99}],
                queue="payments",
                priority=100,
                timeout_ms=60000,
                tags=["payment", "critical"],
                retry=RetryPolicy(
                    max_attempts=5,
                    initial_interval="PT5S",
                    backoff_coefficient=3.0,
                    max_interval="PT10M",
                    non_retryable_errors=["invalid_card", "insufficient_funds"],
                ),
                unique=UniquePolicy(
                    keys=["type", "args"],
                    period="PT1H",
                    on_conflict="reject",
                ),
            )
            return req.to_dict()

        benchmark(build)
