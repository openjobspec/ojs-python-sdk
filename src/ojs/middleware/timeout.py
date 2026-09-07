"""Execution timeout middleware for OJS job processing.

Aborts job execution if it exceeds the configured timeout using
``asyncio.timeout`` (Python 3.11+).

Usage::

    from ojs.middleware.timeout import timeout_middleware

    worker.middleware(timeout_middleware(seconds=30))
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from ojs.errors import JobExecutionTimeout
from ojs.job import JobContext


class TimeoutError(JobExecutionTimeout):  # noqa: A001
    """Deprecated compatibility name for :class:`JobExecutionTimeout`."""


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
        JobExecutionTimeout: If the job exceeds the configured timeout.
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


__all__ = ["JobExecutionTimeout", "TimeoutError", "timeout_middleware"]
