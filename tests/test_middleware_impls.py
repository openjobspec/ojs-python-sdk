"""Tests for OJS common middleware implementations."""

from __future__ import annotations

import asyncio
import logging

import pytest

from ojs.errors import JobExecutionTimeout, OJSError, OJSTimeoutError
from ojs.job import Job, JobContext, JobState
from ojs.middleware.logging import logging_middleware
from ojs.middleware.metrics import metrics_middleware
from ojs.middleware.retry import retry_middleware
from ojs.middleware.timeout import TimeoutError as MiddlewareTimeoutError
from ojs.middleware.timeout import timeout_middleware
from ojs.worker.execution_retry import ExecutionLease, LeaseBudgetExceededError


def _make_ctx() -> JobContext:
    job = Job(id="test-id", type="test.job", state=JobState.ACTIVE, queue="default")
    return JobContext(job=job, attempt=1)


class TestLoggingMiddleware:
    async def test_logs_completion(self, caplog: pytest.LogCaptureFixture) -> None:
        mw = logging_middleware()
        ctx = _make_ctx()

        with caplog.at_level(logging.INFO, logger="ojs"):
            await mw(ctx, _ok_handler)

        assert any("Job completed" in r.message for r in caplog.records)

    async def test_logs_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        mw = logging_middleware()
        ctx = _make_ctx()

        with (
            caplog.at_level(logging.INFO, logger="ojs"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await mw(ctx, _fail_handler)

        assert any("Job failed" in r.message for r in caplog.records)


class TestTimeoutMiddleware:
    async def test_passes_on_fast_job(self) -> None:
        mw = timeout_middleware(seconds=1.0)
        ctx = _make_ctx()

        result = await mw(ctx, _ok_handler)
        assert result == "ok"

    async def test_raises_on_slow_job(self) -> None:
        mw = timeout_middleware(seconds=0.01)
        ctx = _make_ctx()

        async def slow_handler() -> str:
            await asyncio.sleep(1.0)
            return "too late"

        with pytest.raises(JobExecutionTimeout) as raised:
            await mw(ctx, slow_handler)

        assert raised.value.job_id == "test-id"
        assert raised.value.timeout_seconds == 0.01
        assert isinstance(raised.value, OJSTimeoutError)
        assert isinstance(raised.value, OJSError)

    def test_legacy_timeout_name_is_an_alias(self) -> None:
        assert issubclass(MiddlewareTimeoutError, JobExecutionTimeout)


class TestRetryMiddleware:
    async def test_passes_on_success(self) -> None:
        mw = retry_middleware(max_retries=3, base_delay=0.001)
        ctx = _make_ctx()

        result = await mw(ctx, _ok_handler)
        assert result == "ok"

    async def test_retries_and_succeeds(self) -> None:
        mw = retry_middleware(max_retries=3, base_delay=0.001, jitter=False)
        ctx = _make_ctx()

        calls = 0

        async def flaky_handler() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("fail")
            return "ok"

        result = await mw(ctx, flaky_handler)
        assert result == "ok"
        assert calls == 3

    async def test_raises_after_exhausting_retries(self) -> None:
        mw = retry_middleware(max_retries=2, base_delay=0.001, jitter=False)
        ctx = _make_ctx()

        with pytest.raises(RuntimeError, match="always fails"):
            await mw(ctx, _fail_handler_always)

    async def test_retry_stops_at_visibility_budget(self) -> None:
        lease = ExecutionLease(visibility_timeout_ms=10)
        ctx = _make_ctx()
        ctx._retry_sleep = lease.sleep_for_retry
        ctx._lease_remaining = lambda: lease.remaining
        mw = retry_middleware(
            max_retries=2,
            base_delay=0.05,
            jitter=False,
        )
        calls = 0

        async def fail() -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("fail")

        with pytest.raises(LeaseBudgetExceededError):
            await mw(ctx, fail)

        assert calls == 1
        assert ctx.lease_remaining == 0

    async def test_heartbeat_extensions_keep_retry_within_lease(self) -> None:
        lease = ExecutionLease(visibility_timeout_ms=20)
        ctx = _make_ctx()
        ctx._retry_sleep = lease.sleep_for_retry
        ctx._lease_remaining = lambda: lease.remaining
        mw = retry_middleware(
            max_retries=1,
            base_delay=0.05,
            jitter=False,
        )
        calls = 0

        async def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("retry")
            return "ok"

        async def heartbeat() -> None:
            for _ in range(5):
                await asyncio.sleep(0.01)
                lease.extend(20)

        heartbeat_task = asyncio.create_task(heartbeat())
        result = await mw(ctx, flaky)
        await heartbeat_task

        assert result == "ok"
        assert calls == 2

    async def test_cancellation_during_retry_sleep_propagates(self) -> None:
        lease = ExecutionLease(visibility_timeout_ms=1000)
        ctx = _make_ctx()
        ctx._retry_sleep = lease.sleep_for_retry
        mw = retry_middleware(
            max_retries=1,
            base_delay=0.5,
            jitter=False,
        )

        task = asyncio.create_task(mw(ctx, _fail_handler_always))
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestMetricsMiddleware:
    async def test_records_completion(self) -> None:
        recorder = FakeRecorder()
        mw = metrics_middleware(recorder)
        ctx = _make_ctx()

        await mw(ctx, _ok_handler)

        assert recorder.started == 1
        assert recorder.completed == 1
        assert recorder.failed == 0

    async def test_records_failure(self) -> None:
        recorder = FakeRecorder()
        mw = metrics_middleware(recorder)
        ctx = _make_ctx()

        with pytest.raises(RuntimeError):
            await mw(ctx, _fail_handler)

        assert recorder.started == 1
        assert recorder.failed == 1
        assert recorder.completed == 0

    @pytest.mark.parametrize("phase", ["started", "completed"])
    async def test_recorder_failures_do_not_fail_successful_jobs(
        self,
        phase: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        recorder = FailingRecorder(phase)
        mw = metrics_middleware(recorder)

        with caplog.at_level(logging.ERROR, logger="ojs.middleware.metrics"):
            result = await mw(_make_ctx(), _ok_handler)

        assert result == "ok"
        assert any(phase in record.message for record in caplog.records)

    async def test_failure_recorder_error_preserves_handler_error(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        recorder = FailingRecorder("failed")
        mw = metrics_middleware(recorder)

        with (
            caplog.at_level(logging.ERROR, logger="ojs.middleware.metrics"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await mw(_make_ctx(), _fail_handler)

        assert any("job_failed" in record.message for record in caplog.records)

    async def test_fail_closed_propagates_start_recorder_error(self) -> None:
        recorder = FailingRecorder("started")
        mw = metrics_middleware(recorder, fail_open=False)
        handler_called = False

        async def handler() -> str:
            nonlocal handler_called
            handler_called = True
            return "ok"

        with pytest.raises(RecorderError, match="started"):
            await mw(_make_ctx(), handler)

        assert handler_called is False

    async def test_fail_closed_propagates_completion_recorder_error(self) -> None:
        recorder = FailingRecorder("completed")
        mw = metrics_middleware(recorder, fail_open=False)

        with pytest.raises(RecorderError, match="completed"):
            await mw(_make_ctx(), _ok_handler)

    async def test_fail_closed_chains_handler_error_on_failure_recorder_error(
        self,
    ) -> None:
        recorder = FailingRecorder("failed")
        mw = metrics_middleware(recorder, fail_open=False)

        with pytest.raises(RecorderError, match="failed") as raised:
            await mw(_make_ctx(), _fail_handler)

        assert isinstance(raised.value.__cause__, RuntimeError)
        assert str(raised.value.__cause__) == "boom"


# -- Helpers --


async def _ok_handler() -> str:
    return "ok"


async def _fail_handler() -> str:
    raise RuntimeError("boom")


async def _fail_handler_always() -> str:
    raise RuntimeError("always fails")


class FakeRecorder:
    """Simple in-memory MetricsRecorder for testing."""

    def __init__(self) -> None:
        self.started = 0
        self.completed = 0
        self.failed = 0

    def job_started(self, job_type: str, queue: str) -> None:
        self.started += 1

    def job_completed(self, job_type: str, queue: str, duration_s: float) -> None:
        self.completed += 1

    def job_failed(self, job_type: str, queue: str, duration_s: float, error: Exception) -> None:
        self.failed += 1


class RecorderError(RuntimeError):
    pass


class FailingRecorder(FakeRecorder):
    def __init__(self, phase: str) -> None:
        super().__init__()
        self._phase = phase

    def job_started(self, job_type: str, queue: str) -> None:
        if self._phase == "started":
            raise RecorderError("started recorder failure")
        super().job_started(job_type, queue)

    def job_completed(self, job_type: str, queue: str, duration_s: float) -> None:
        if self._phase == "completed":
            raise RecorderError("completed recorder failure")
        super().job_completed(job_type, queue, duration_s)

    def job_failed(
        self,
        job_type: str,
        queue: str,
        duration_s: float,
        error: Exception,
    ) -> None:
        if self._phase == "failed":
            raise RecorderError("failed recorder failure")
        super().job_failed(job_type, queue, duration_s, error)
