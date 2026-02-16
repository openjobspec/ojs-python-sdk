"""Benchmark tests for OJS Python SDK core operations.

Run with: pytest tests/test_benchmark.py -v
"""

import json
import time

import pytest

from ojs.job import Job, JobRequest, JobState


MINIMAL_JOB_DICT = {
    "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "type": "email.send",
    "state": "available",
    "queue": "default",
    "args": [{"to": "user@example.com"}],
    "attempt": 0,
    "created_at": "2024-01-15T10:30:00Z",
}

FULL_JOB_DICT = {
    "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
    "type": "email.send",
    "state": "active",
    "queue": "email",
    "args": [{"to": "user@example.com", "subject": "Welcome!"}],
    "priority": 10,
    "attempt": 2,
    "max_retries": 5,
    "tags": ["onboarding", "email"],
    "meta": {"campaign_id": "123", "source": "api"},
    "created_at": "2024-01-15T10:30:00Z",
    "scheduled_at": "2024-01-15T11:00:00Z",
}


class TestJobDeserialization:
    """Benchmark Job.from_dict() for various payload sizes."""

    def test_bench_from_dict_minimal(self) -> None:
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            Job.from_dict(MINIMAL_JOB_DICT)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000  # microseconds
        print(f"\n  Job.from_dict (minimal): {per_op:.2f} µs/op ({iterations} iterations)")
        assert per_op < 1000, f"Too slow: {per_op:.2f} µs/op"

    def test_bench_from_dict_full(self) -> None:
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            Job.from_dict(FULL_JOB_DICT)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  Job.from_dict (full): {per_op:.2f} µs/op ({iterations} iterations)")
        assert per_op < 1000, f"Too slow: {per_op:.2f} µs/op"


class TestJobRequestSerialization:
    """Benchmark JobRequest.to_dict() for various payload sizes."""

    def test_bench_to_dict_minimal(self) -> None:
        req = JobRequest(type="email.send", args=["user@example.com"])
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            req.to_dict()
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  JobRequest.to_dict (minimal): {per_op:.2f} µs/op ({iterations} iterations)")
        assert per_op < 1000, f"Too slow: {per_op:.2f} µs/op"

    def test_bench_to_dict_full(self) -> None:
        req = JobRequest(
            type="email.send",
            args=["user@example.com", "Welcome!"],
            queue="email",
            priority=10,
            tags=["onboarding"],
        )
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            req.to_dict()
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  JobRequest.to_dict (full): {per_op:.2f} µs/op ({iterations} iterations)")
        assert per_op < 1000, f"Too slow: {per_op:.2f} µs/op"


class TestJsonSerialization:
    """Benchmark raw JSON serialization round-trips."""

    def test_bench_json_dumps_minimal(self) -> None:
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            json.dumps(MINIMAL_JOB_DICT)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  json.dumps (minimal): {per_op:.2f} µs/op ({iterations} iterations)")

    def test_bench_json_dumps_full(self) -> None:
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            json.dumps(FULL_JOB_DICT)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  json.dumps (full): {per_op:.2f} µs/op ({iterations} iterations)")

    def test_bench_json_loads_minimal(self) -> None:
        data = json.dumps(MINIMAL_JOB_DICT)
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            json.loads(data)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  json.loads (minimal): {per_op:.2f} µs/op ({iterations} iterations)")

    def test_bench_json_loads_full(self) -> None:
        data = json.dumps(FULL_JOB_DICT)
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            json.loads(data)
        elapsed = time.perf_counter() - start
        per_op = elapsed / iterations * 1_000_000
        print(f"\n  json.loads (full): {per_op:.2f} µs/op ({iterations} iterations)")


class TestJobStateOperations:
    """Benchmark state-related operations."""

    def test_bench_is_terminal(self) -> None:
        states = list(JobState)
        iterations = 100_000
        start = time.perf_counter()
        for _ in range(iterations):
            for s in states:
                s.is_terminal()
        elapsed = time.perf_counter() - start
        per_op = elapsed / (iterations * len(states)) * 1_000_000
        print(f"\n  JobState.is_terminal: {per_op:.2f} µs/op ({iterations * len(states)} iterations)")
