"""Metrics recording middleware for OJS job processing.

Provides a pluggable ``MetricsRecorder`` protocol for recording
job execution metrics to any backend.

Usage::

    from ojs.middleware.metrics import MetricsRecorder, metrics_middleware

    class MyRecorder:
        def job_started(self, job_type: str, queue: str) -> None: ...
        def job_completed(self, job_type: str, queue: str, duration_s: float) -> None: ...
        def job_failed(
            self, job_type: str, queue: str, duration_s: float, error: Exception
        ) -> None: ...

    worker.middleware(metrics_middleware(MyRecorder()))
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Protocol, runtime_checkable

from ojs.job import JobContext

logger = logging.getLogger("ojs.middleware.metrics")


@runtime_checkable
class MetricsRecorder(Protocol):
    """Protocol for recording job execution metrics.

    Implement this protocol to forward metrics to Prometheus,
    StatsD, Datadog, or any other metrics system.
    """

    def job_started(self, job_type: str, queue: str) -> None:
        """Called when a job starts processing."""
        ...

    def job_completed(self, job_type: str, queue: str, duration_s: float) -> None:
        """Called when a job completes successfully."""
        ...

    def job_failed(self, job_type: str, queue: str, duration_s: float, error: Exception) -> None:
        """Called when a job fails."""
        ...


def metrics_middleware(
    recorder: MetricsRecorder,
    *,
    fail_open: bool = True,
) -> Callable[[JobContext, Callable[[], Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
    """Create execution middleware that records job metrics.

    Args:
        recorder: A :class:`MetricsRecorder` implementation.
        fail_open: If true, log recorder failures without affecting job
            execution. If false, propagate recorder failures.

    Returns:
        Async execution middleware function.
    """

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        job_type = ctx.job.type
        queue = ctx.job.queue

        start = time.monotonic()
        _record_metric(
            "job_started",
            lambda: recorder.job_started(job_type, queue),
            fail_open=fail_open,
        )

        try:
            result = await next_handler()
        except Exception as exc:
            duration = time.monotonic() - start
            try:
                _record_metric(
                    "job_failed",
                    partial(recorder.job_failed, job_type, queue, duration, exc),
                    fail_open=fail_open,
                )
            except Exception as recorder_error:
                raise recorder_error from exc
            raise
        duration = time.monotonic() - start
        _record_metric(
            "job_completed",
            lambda: recorder.job_completed(job_type, queue, duration),
            fail_open=fail_open,
        )
        return result

    return middleware


def _record_metric(
    phase: str,
    record: Callable[[], None],
    *,
    fail_open: bool,
) -> None:
    try:
        record()
    except Exception:
        if not fail_open:
            raise
        logger.exception("Metrics recorder failed during %s; continuing job execution", phase)
