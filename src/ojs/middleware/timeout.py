"""Execution timeout middleware for OJS job processing.

Aborts job execution if it exceeds the configured timeout using
``asyncio.timeout`` (Python 3.11+).

Usage::

    from ojs.middleware.timeout import timeout_middleware

    worker.add_middleware(timeout_middleware(seconds=30))
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import JobContext


class TimeoutError(Exception):  # noqa: A001
    """Raised when a job exceeds its execution timeout.

    Attributes:
        timeout_seconds: The configured timeout in seconds.
        job_id: The ID of the job that timed out.
    """

    def __init__(self, timeout_seconds: float, job_id: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.job_id = job_id
        super().__init__(f"Job {job_id} timed out after {timeout_seconds}s")


def timeout_middleware(
    *,
    seconds: float,
) -> Callable[[JobContext, Callable[[], Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
    """Create execution middleware that enforces a timeout on job processing.

    Args:
        seconds: Maximum execution time in seconds.

    Returns:
        Async execution middleware function.

    Raises:
        TimeoutError: If the job exceeds the configured timeout.
    """

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        try:
            async with asyncio.timeout(seconds):
                return await next_handler()
        except asyncio.TimeoutError:  # noqa: UP041
            raise TimeoutError(seconds, ctx.job.id) from None

    return middleware
