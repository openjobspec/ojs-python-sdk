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

    worker.add_middleware(metrics_middleware(MyRecorder()))
"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable

from ojs.job import JobContext


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
) -> Callable[[JobContext, Callable[[], Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
    """Create execution middleware that records job metrics.

    Args:
        recorder: A :class:`MetricsRecorder` implementation.

    Returns:
        Async execution middleware function.
    """

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        job_type = ctx.job.type
        queue = ctx.job.queue

        recorder.job_started(job_type, queue)
        start = time.monotonic()

        try:
            result = await next_handler()
            duration = time.monotonic() - start
            recorder.job_completed(job_type, queue, duration)
            return result
        except Exception as exc:
            duration = time.monotonic() - start
            recorder.job_failed(job_type, queue, duration, exc)
            raise

    return middleware
