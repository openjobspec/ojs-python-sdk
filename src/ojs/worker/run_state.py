"""State owned by one invocation of ``Worker.start``."""

from __future__ import annotations

import asyncio

from ojs.worker.execution_registry import ExecutionRegistry
from ojs.worker.lease_admission import LeaseAdmission


class WorkerRunState:
    """Own shutdown, admission, and execution state for a single run."""

    def __init__(self, concurrency: int) -> None:
        self.shutdown = asyncio.Event()
        self.admission = LeaseAdmission(concurrency)
        self.executions = ExecutionRegistry(self.admission)

    def request_shutdown(self) -> None:
        self.shutdown.set()

    async def wait_or_timeout(self, delay: float) -> bool:
        """Return true when shutdown interrupts the requested delay."""
        if self.shutdown.is_set():
            return True
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True


__all__ = ["WorkerRunState"]
