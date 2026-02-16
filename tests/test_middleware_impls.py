"""Tests for OJS common middleware implementations."""

from __future__ import annotations

import asyncio
import logging

import pytest

from ojs.job import Job, JobContext, JobState
from ojs.middleware.logging import logging_middleware
from ojs.middleware.metrics import MetricsRecorder, metrics_middleware
from ojs.middleware.retry import retry_middleware
from ojs.middleware.timeout import TimeoutError as MiddlewareTimeoutError
from ojs.middleware.timeout import timeout_middleware


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

        with caplog.at_level(logging.INFO, logger="ojs"):
            with pytest.raises(RuntimeError, match="boom"):
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

        with pytest.raises(MiddlewareTimeoutError):
            await mw(ctx, slow_handler)


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
