"""Single-outcome terminal delivery for worker executions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

from ojs.errors import OJSAPIError, OJSConnectionError, OJSTimeoutError


class CompletionTransport(Protocol):
    async def ack(self, job_id: str, result: Any = None) -> Mapping[str, Any]: ...

    async def nack(
        self,
        job_id: str,
        error: dict[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Completed:
    result: object = None


@dataclass(frozen=True, slots=True)
class Failed:
    error: dict[str, Any]


TerminalOutcome: TypeAlias = Completed | Failed


class CompletionReporter:
    """Atomically claim and deliver one terminal outcome for an execution."""

    def __init__(
        self,
        transport: CompletionTransport,
        job_id: str,
        *,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._transport = transport
        self._job_id = job_id
        self._max_attempts = max_attempts
        self._sleep = sleep or asyncio.sleep
        self._claim_lock = asyncio.Lock()
        self._outcome: TerminalOutcome | None = None

    @property
    def outcome(self) -> TerminalOutcome | None:
        return self._outcome

    async def report(self, outcome: TerminalOutcome) -> bool:
        """Claim and deliver an outcome; return false when another already won."""
        async with self._claim_lock:
            if self._outcome is not None:
                return False
            self._outcome = outcome

        await self._deliver(outcome)
        return True

    async def _deliver(self, outcome: TerminalOutcome) -> None:
        for attempt in range(self._max_attempts):
            try:
                if isinstance(outcome, Completed):
                    await self._transport.ack(self._job_id, result=outcome.result)
                else:
                    await self._transport.nack(self._job_id, outcome.error)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= self._max_attempts - 1 or not _retryable_delivery(exc):
                    raise
                await self._sleep((attempt + 1) * 0.5)


def _retryable_delivery(error: Exception) -> bool:
    if isinstance(error, (OJSConnectionError, OJSTimeoutError)):
        return True
    return isinstance(error, OJSAPIError) and error.retryable


__all__ = [
    "Completed",
    "CompletionReporter",
    "CompletionTransport",
    "Failed",
    "TerminalOutcome",
]
