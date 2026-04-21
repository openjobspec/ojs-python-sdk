"""Local handler retries constrained by the active worker lease."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ojs.job import JobContext


class LeaseBudgetExceededError(RuntimeError):
    """A local retry would continue beyond the worker's active lease."""


class ExecutionLease:
    """A monotonic lease deadline that heartbeat responses can extend."""

    def __init__(
        self,
        visibility_timeout_ms: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if visibility_timeout_ms < 1:
            raise ValueError("visibility_timeout_ms must be at least 1")
        self._visibility_seconds = visibility_timeout_ms / 1000
        self._clock = clock
        self._sleep = sleep
        self._deadline = clock() + self._visibility_seconds
        self._extended = asyncio.Event()

    @property
    def remaining(self) -> float:
        return max(0.0, self._deadline - self._clock())

    def extend(self, visibility_timeout_ms: int | None = None) -> None:
        duration = (
            self._visibility_seconds
            if visibility_timeout_ms is None
            else visibility_timeout_ms / 1000
        )
        self._deadline = max(self._deadline, self._clock() + duration)
        self._extended.set()

    async def sleep_for_retry(self, delay: float) -> None:
        """Sleep while heartbeat extensions keep the lease alive."""
        if delay < 0:
            raise ValueError("retry delay cannot be negative")
        target = self._clock() + delay
        while True:
            remaining_delay = target - self._clock()
            if remaining_delay <= 0:
                return
            remaining_lease = self.remaining
            if remaining_lease <= 0:
                raise LeaseBudgetExceededError("local retry delay exhausted the worker lease")

            self._extended.clear()
            delay_task: asyncio.Future[None] = asyncio.ensure_future(
                self._sleep(min(remaining_delay, remaining_lease))
            )
            extension_task = asyncio.create_task(self._extended.wait())
            try:
                done, _ = await asyncio.wait(
                    (delay_task, extension_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                delay_task.cancel()
                extension_task.cancel()
                await asyncio.gather(
                    delay_task,
                    extension_task,
                    return_exceptions=True,
                )
                raise

            if extension_task in done:
                delay_task.cancel()
                await asyncio.gather(delay_task, return_exceptions=True)
                continue
            extension_task.cancel()
            await asyncio.gather(extension_task, return_exceptions=True)
            if self._clock() < target and self.remaining <= 0:
                raise LeaseBudgetExceededError("local retry delay exhausted the worker lease")


@dataclass(frozen=True, slots=True)
class ExecutionRetry:
    """Execute local retries separately from the server-side RetryPolicy."""

    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = 30.0
    jitter: bool = True
    random_value: Callable[[], float] = random.random

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.base_delay < 0:
            raise ValueError("base_delay cannot be negative")
        if self.max_delay < 0:
            raise ValueError("max_delay cannot be negative")

    async def run(
        self,
        context: JobContext,
        next_handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return await next_handler()
            except Exception:
                if attempt >= self.max_retries:
                    raise
                await context.sleep_before_retry(self._delay(attempt))
        raise RuntimeError("execution retry loop ended unexpectedly")

    def _delay(self, attempt: int) -> float:
        capped = float(min(self.base_delay * (2**attempt), self.max_delay))
        if not self.jitter:
            return capped
        return float(capped * (0.5 + self.random_value() * 0.5))


__all__ = ["ExecutionLease", "ExecutionRetry", "LeaseBudgetExceededError"]
