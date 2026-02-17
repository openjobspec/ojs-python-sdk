"""Property-based / fuzz tests for the OJS Python SDK.

Uses Hypothesis to generate arbitrary inputs and verify that the SDK
handles them without crashing. Modeled after ojs-go-sdk/fuzz_test.go.
"""

from __future__ import annotations

import json
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ojs.errors import OJSAPIError, raise_for_error
from ojs.job import Job, JobContext, JobRequest, JobState
from ojs.middleware import EnqueueMiddlewareChain, ExecutionMiddlewareChain
from ojs.retry import RetryPolicy

# ---------------------------------------------------------------------------
# Reusable strategies
# ---------------------------------------------------------------------------

# JSON-safe primitive values (mirrors what OJS args can contain)
json_primitives = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
)

# Recursive strategy for nested JSON-safe values
json_values = st.recursive(
    json_primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=15,
)

# Strategy for OJS args: a list of mixed JSON-safe values
args_strategy = st.lists(json_values, max_size=8)

# Strategy for valid OJS states (as raw strings)
job_state_values = st.sampled_from([s.value for s in JobState])


# ---------------------------------------------------------------------------
# 1. Job JSON roundtrip
# ---------------------------------------------------------------------------


class TestJobJsonRoundtrip:
    """Generate arbitrary job dicts, serialize → deserialize, verify equality.

    Mirrors FuzzJobMarshalRoundTrip and FuzzJobUnmarshalJSON from the Go SDK.
    """

    @given(
        job_id=st.text(min_size=1, max_size=50),
        job_type=st.text(min_size=1, max_size=50),
        state=job_state_values,
        args=args_strategy,
        queue=st.text(min_size=1, max_size=30),
        priority=st.integers(min_value=-100, max_value=100),
        attempt=st.integers(min_value=0, max_value=100),
        max_attempts=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    def test_job_from_dict_roundtrip(
        self,
        job_id: str,
        job_type: str,
        state: str,
        args: list[Any],
        queue: str,
        priority: int,
        attempt: int,
        max_attempts: int,
    ) -> None:
        """Job.from_dict should never crash and should preserve core fields."""
        data: dict[str, Any] = {
            "id": job_id,
            "type": job_type,
            "state": state,
            "args": args,
            "queue": queue,
            "priority": priority,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }
        job = Job.from_dict(data)
        assert job.id == job_id
        assert job.type == job_type
        assert job.state == JobState(state)
        assert job.queue == queue
        assert job.priority == priority

    @given(data=st.binary(min_size=0, max_size=200))
    @settings(max_examples=200)
    def test_job_from_dict_never_crashes_on_valid_json(self, data: bytes) -> None:
        """Parsing arbitrary bytes as JSON and feeding to Job.from_dict must not panic.

        If the bytes aren't valid JSON or lack required fields, exceptions are
        expected — but never an unhandled crash.
        """
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return  # not valid JSON — not interesting

        if not isinstance(parsed, dict):
            return

        # Ensure required fields so from_dict doesn't KeyError on expected keys
        parsed.setdefault("id", "")
        parsed.setdefault("type", "")
        parsed.setdefault("state", "available")

        try:
            job = Job.from_dict(parsed)
            # If deserialization succeeded, accessing fields must not crash
            _ = job.id
            _ = job.type
            _ = job.state
            _ = job.args
        except (ValueError, TypeError, KeyError):
            pass  # acceptable parse failures


# ---------------------------------------------------------------------------
# 2. Args serialization roundtrip
# ---------------------------------------------------------------------------


class TestArgsSerialization:
    """Generate lists of mixed types, ensure JSON serialization roundtrip.

    Mirrors FuzzArgsFromWire from the Go SDK.
    """

    @given(args=args_strategy)
    @settings(max_examples=200)
    def test_args_json_roundtrip(self, args: list[Any]) -> None:
        """args → JSON → args should produce equal results."""
        serialized = json.dumps(args)
        deserialized = json.loads(serialized)
        assert deserialized == args

    @given(args=args_strategy)
    @settings(max_examples=200)
    def test_job_request_args_survive_to_dict(self, args: list[Any]) -> None:
        """JobRequest.to_dict should preserve args without crashing."""
        req = JobRequest(type="test.fuzz", args=args)
        d = req.to_dict()
        assert d["args"] == args

        # The dict should be JSON-serializable
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped["args"] == args

    @given(
        args=st.lists(
            st.one_of(
                st.text(max_size=20),
                st.integers(min_value=-(2**31), max_value=2**31),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
                st.none(),
                st.dictionaries(st.text(max_size=5), st.text(max_size=10), max_size=3),
                st.lists(st.integers(), max_size=3),
            ),
            max_size=10,
        )
    )
    @settings(max_examples=200)
    def test_nested_args_serialization(self, args: list[Any]) -> None:
        """Deeply nested args should serialize and deserialize cleanly."""
        req = JobRequest(type="nested.test", args=args)
        body = req.to_dict()
        raw = json.dumps(body)
        restored = json.loads(raw)
        assert restored["args"] == args


# ---------------------------------------------------------------------------
# 3. Validation fuzzing
# ---------------------------------------------------------------------------


class TestValidationFuzzing:
    """Generate random strings for job type/queue, verify consistent behavior.

    Mirrors FuzzValidateEnqueueParams and FuzzValidateQueue from the Go SDK.
    """

    @given(
        job_type=st.text(max_size=300),
        queue=st.text(max_size=200),
    )
    @settings(max_examples=200)
    def test_job_request_creation_never_crashes(
        self, job_type: str, queue: str
    ) -> None:
        """Creating a JobRequest with arbitrary type/queue must not crash."""
        req = JobRequest(type=job_type, args=[], queue=queue)
        # to_dict must not crash regardless of input
        d = req.to_dict()
        assert d["type"] == job_type

    @given(
        job_type=st.text(max_size=100),
        args=args_strategy,
        queue=st.text(max_size=100),
        priority=st.integers(min_value=-1000, max_value=1000),
        timeout_ms=st.one_of(st.none(), st.integers(min_value=0, max_value=10**9)),
    )
    @settings(max_examples=200)
    def test_job_request_to_dict_always_valid_json(
        self,
        job_type: str,
        args: list[Any],
        queue: str,
        priority: int,
        timeout_ms: int | None,
    ) -> None:
        """JobRequest.to_dict() output must always be JSON-serializable."""
        req = JobRequest(
            type=job_type,
            args=args,
            queue=queue,
            priority=priority,
            timeout_ms=timeout_ms,
        )
        d = req.to_dict()
        # Must not raise
        raw = json.dumps(d)
        assert isinstance(json.loads(raw), dict)

    @given(state_str=st.text(max_size=30))
    @settings(max_examples=200)
    def test_job_state_parsing_consistent(self, state_str: str) -> None:
        """JobState() should either return a valid state or raise ValueError."""
        try:
            state = JobState(state_str)
            assert state.value == state_str
        except ValueError:
            pass  # expected for invalid state strings


# ---------------------------------------------------------------------------
# 4. Error parsing
# ---------------------------------------------------------------------------


class TestErrorParsing:
    """Generate arbitrary dicts as error responses, ensure parsing doesn't crash.

    Ensures raise_for_error handles malformed/unexpected server responses.
    """

    @given(
        status_code=st.integers(min_value=100, max_value=599),
        error_code=st.text(max_size=30),
        message=st.text(max_size=100),
        retryable=st.booleans(),
    )
    @settings(max_examples=200)
    def test_raise_for_error_structured(
        self, status_code: int, error_code: str, message: str, retryable: bool
    ) -> None:
        """raise_for_error with well-formed error bodies must not crash."""
        body: dict[str, Any] = {
            "error": {
                "code": error_code,
                "message": message,
                "retryable": retryable,
            }
        }
        try:
            raise_for_error(status_code, body, None)
        except OJSAPIError as e:
            assert e.status_code == status_code
            assert e.error.code == error_code

    @given(body=st.dictionaries(st.text(max_size=20), json_values, max_size=5))
    @settings(max_examples=200)
    def test_raise_for_error_arbitrary_body(self, body: dict[str, Any]) -> None:
        """raise_for_error must not crash on arbitrary dict bodies."""
        try:
            raise_for_error(500, body, None)
        except OJSAPIError:
            pass  # expected

    @given(
        headers=st.one_of(
            st.none(),
            st.dictionaries(st.text(max_size=20), st.text(max_size=20), max_size=5),
        )
    )
    @settings(max_examples=200)
    def test_raise_for_error_arbitrary_headers(
        self, headers: dict[str, str] | None
    ) -> None:
        """raise_for_error must handle arbitrary header dicts gracefully."""
        body: dict[str, Any] = {
            "error": {
                "code": "rate_limited",
                "message": "slow down",
                "retryable": True,
            }
        }
        try:
            raise_for_error(429, body, headers)
        except OJSAPIError:
            pass  # expected

    @given(body=st.just({}))
    @settings(max_examples=5)
    def test_raise_for_error_empty_body(self, body: dict[str, Any]) -> None:
        """An empty body should produce an error with sensible defaults."""
        try:
            raise_for_error(500, body, None)
        except OJSAPIError as e:
            assert e.error.code == "unknown"
            assert e.error.retryable is False


# ---------------------------------------------------------------------------
# 5. Middleware chain
# ---------------------------------------------------------------------------


class TestMiddlewareChainFuzz:
    """Generate random middleware stacks, ensure chain execution completes.

    Tests both EnqueueMiddlewareChain and ExecutionMiddlewareChain with
    varying numbers of middleware functions.
    """

    @given(n=st.integers(min_value=0, max_value=20))
    @settings(max_examples=50)
    async def test_enqueue_chain_with_n_middlewares(self, n: int) -> None:
        """An enqueue chain with N pass-through middlewares must complete."""
        chain = EnqueueMiddlewareChain()
        call_order: list[int] = []

        for i in range(n):
            idx = i  # capture loop variable

            async def mw(
                request: JobRequest, nxt: Any, *, _idx: int = idx
            ) -> Job | None:
                call_order.append(_idx)
                return await nxt(request)

            chain.add(mw)

        async def final(req: JobRequest) -> Job:
            return Job(
                id="fuzz", type=req.type, state=JobState.AVAILABLE, args=req.args
            )

        result = await chain.execute(
            JobRequest(type="fuzz.test", args=[1, 2]), final
        )
        assert result is not None
        assert result.type == "fuzz.test"
        assert call_order == list(range(n))

    @given(n=st.integers(min_value=0, max_value=20))
    @settings(max_examples=50)
    async def test_execution_chain_with_n_middlewares(self, n: int) -> None:
        """An execution chain with N pass-through middlewares must complete."""
        chain = ExecutionMiddlewareChain()
        call_order: list[int] = []

        for i in range(n):
            idx = i

            async def mw(
                ctx: JobContext, nxt: Any, *, _idx: int = idx
            ) -> Any:
                call_order.append(_idx)
                return await nxt()

            chain.add(mw)

        job = Job(id="fuzz", type="fuzz.test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        result = await chain.execute(ctx, handler)
        assert result == "done"
        assert call_order == list(range(n))

    @given(
        n=st.integers(min_value=1, max_value=10),
        error_at=st.integers(min_value=0, max_value=9),
    )
    @settings(max_examples=50)
    async def test_execution_chain_error_propagation(
        self, n: int, error_at: int
    ) -> None:
        """Errors raised in middleware should propagate without crashing."""
        chain = ExecutionMiddlewareChain()
        actual_error_at = error_at % n  # ensure within bounds

        for i in range(n):
            idx = i

            async def mw(
                ctx: JobContext, nxt: Any, *, _idx: int = idx
            ) -> Any:
                if _idx == actual_error_at:
                    raise ValueError(f"fuzz error at {_idx}")
                return await nxt()

            chain.add(mw)

        job = Job(id="fuzz", type="fuzz.test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        try:
            await chain.execute(ctx, handler)
        except ValueError as e:
            assert f"fuzz error at {actual_error_at}" in str(e)


# ---------------------------------------------------------------------------
# 6. RetryPolicy roundtrip
# ---------------------------------------------------------------------------


class TestRetryPolicyFuzz:
    """Fuzz RetryPolicy serialization and delay computation."""

    @given(
        max_attempts=st.integers(min_value=1, max_value=100),
        backoff=st.floats(min_value=1.0, max_value=10.0, allow_nan=False),
        jitter=st.booleans(),
    )
    @settings(max_examples=200)
    def test_retry_policy_roundtrip(
        self, max_attempts: int, backoff: float, jitter: bool
    ) -> None:
        """RetryPolicy.to_dict → from_dict should preserve fields."""
        policy = RetryPolicy(
            max_attempts=max_attempts,
            backoff_coefficient=backoff,
            jitter=jitter,
        )
        d = policy.to_dict()
        restored = RetryPolicy.from_dict(d)
        assert restored.max_attempts == max_attempts
        assert restored.backoff_coefficient == backoff
        assert restored.jitter == jitter

    @given(attempt=st.integers(min_value=1, max_value=50))
    @settings(max_examples=100)
    def test_delay_for_attempt_never_crashes(self, attempt: int) -> None:
        """delay_for_attempt must return a non-negative float."""
        policy = RetryPolicy()
        delay = policy.delay_for_attempt(attempt)
        assert isinstance(delay, float)
        assert delay >= 0
