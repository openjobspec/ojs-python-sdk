"""Structured logging middleware for OJS job processing.

Logs job start, completion, and failure events with timing information
using Python's standard ``logging`` module.

Usage::

    from ojs.middleware.logging import logging_middleware

    worker.add_middleware(logging_middleware())
    worker.add_middleware(logging_middleware(level="DEBUG"))
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import JobContext

logger = logging.getLogger("ojs")


def logging_middleware(
    *,
    log_level: int = logging.INFO,
    custom_logger: logging.Logger | None = None,
) -> Callable[[JobContext, Callable[[], Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
    """Create execution middleware that logs job lifecycle events.

    Args:
        log_level: The logging level for start/completion messages.
            Defaults to ``logging.INFO``.
        custom_logger: Optional custom logger instance. Defaults to
            the ``ojs`` logger.

    Returns:
        Async execution middleware function.
    """
    log = custom_logger or logger

    async def middleware(
        ctx: JobContext,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        job = ctx.job
        log.log(
            log_level,
            "Job started: %s (id=%s, attempt=%d)",
            job.type,
            job.id,
            ctx.attempt,
        )

        start = time.monotonic()
        try:
            result = await next_handler()
            elapsed = time.monotonic() - start
            log.log(
                log_level,
                "Job completed: %s (id=%s, %.2fms)",
                job.type,
                job.id,
                elapsed * 1000,
            )
            return result
        except Exception:
            elapsed = time.monotonic() - start
            log.exception(
                "Job failed: %s (id=%s, %.2fms)",
                job.type,
                job.id,
                elapsed * 1000,
            )
            raise

    return middleware
