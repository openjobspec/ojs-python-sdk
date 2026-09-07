"""Retry middleware for OJS job processing.

Retries failed job executions with configurable exponential backoff and jitter.

Usage::

    from ojs.middleware.retry import retry_middleware

    worker.middleware(retry_middleware(max_retries=3))
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import JobContext
from ojs.worker.execution_retry import ExecutionRetry


def retry_middleware(
    *,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> Callable[[JobContext, Callable[[], Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
    """Create execution middleware that retries failed job executions.

    Uses exponential backoff with optional jitter between retry attempts.

    Args:
        max_retries: Maximum number of retry attempts. Defaults to ``3``.
        base_delay: Base delay in seconds for exponential backoff.
            Defaults to ``0.1``.
        max_delay: Maximum delay in seconds. Defaults to ``30.0``.
        jitter: Whether to add random jitter to the delay. Defaults to
            ``True``.

    Returns:
        Async execution middleware function.
    """

    retry = ExecutionRetry(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
    )

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        return await retry.run(ctx, next_handler)

    return middleware
