"""Retry middleware for OJS job processing.

Retries failed job executions with configurable exponential backoff and jitter.

Usage::

    from ojs.middleware.retry import retry_middleware

    worker.add_middleware(retry_middleware(max_retries=3))
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import JobContext


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

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        last_error: BaseException | None = None

        for attempt in range(max_retries + 1):
            try:
                return await next_handler()
            except Exception as exc:
                last_error = exc

                if attempt >= max_retries:
                    break

                exponential_delay = base_delay * (2**attempt)
                capped_delay = min(exponential_delay, max_delay)
                final_delay = (
                    capped_delay * (0.5 + random.random() * 0.5)  # noqa: S311
                    if jitter
                    else capped_delay
                )
                await asyncio.sleep(final_delay)

        raise last_error  # type: ignore[misc]

    return middleware
