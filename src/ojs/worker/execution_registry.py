"""Run-scoped worker execution ownership."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ojs.worker.execution_retry import ExecutionLease
from ojs.worker.lease_admission import LeaseAdmission, LeasePermit


@dataclass(frozen=True, slots=True)
class ActiveExecution:
    """A uniquely tracked execution, independent of its backend job ID."""

    token: str
    job_id: str
    task: asyncio.Task[None]
    permit: LeasePermit
    lease: ExecutionLease


class ExecutionRegistry:
    """Track active tasks by execution token and release admission exactly once."""

    def __init__(self, admission: LeaseAdmission) -> None:
        self._admission = admission
        self._executions: dict[str, ActiveExecution] = {}
        self._empty = asyncio.Event()
        self._empty.set()

    def register(
        self,
        *,
        job_id: str,
        task: asyncio.Task[None],
        permit: LeasePermit,
        lease: ExecutionLease,
    ) -> ActiveExecution:
        execution = ActiveExecution(
            token=permit.token,
            job_id=job_id,
            task=task,
            permit=permit,
            lease=lease,
        )
        if execution.token in self._executions:
            raise RuntimeError(f"duplicate execution token: {execution.token}")
        self._executions[execution.token] = execution
        self._empty.clear()
        return execution

    def complete(self, token: str) -> bool:
        execution = self._executions.pop(token, None)
        if execution is None:
            return False
        self._admission.release(execution.permit)
        if not self._executions:
            self._empty.set()
        return True

    def active_job_ids(self) -> list[str]:
        """Return one lease ID per execution, preserving duplicate job IDs."""
        return [execution.job_id for execution in self._executions.values()]

    def active_tasks(self) -> tuple[asyncio.Task[None], ...]:
        return tuple(execution.task for execution in self._executions.values())

    def extend_leases(
        self,
        visibility_timeout_ms: int,
        *,
        job_ids: set[str] | None = None,
    ) -> None:
        for execution in self._executions.values():
            if job_ids is None or execution.job_id in job_ids:
                execution.lease.extend(visibility_timeout_ms)

    async def wait_empty(self) -> None:
        await self._empty.wait()

    def __len__(self) -> int:
        return len(self._executions)


__all__ = ["ActiveExecution", "ExecutionRegistry"]
