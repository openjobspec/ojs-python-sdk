"""Explicit in-memory transport for tests and local simulations."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ojs.errors import OJSCapabilityError
from ojs.job import Job, JobState
from ojs.queue import Queue, QueueStats
from ojs.transport.base import Transport
from ojs.workflow import Workflow, WorkflowDefinition


@dataclass
class FakeJob:
    """A job recorded by ``FakeTransport``."""

    id: str
    type: str
    queue: str
    args: list[Any]
    meta: dict[str, Any]
    state: str = "available"
    attempt: int = 0
    options: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


class FakeStore:
    """In-memory fake job store owned by one transport."""

    def __init__(self) -> None:
        self.enqueued: list[FakeJob] = []
        self.performed: list[FakeJob] = []
        self.handlers: dict[str, Callable[[FakeJob], None]] = {}
        self._next_id = 0

    def record_enqueue(
        self,
        job_type: str,
        args: list[Any],
        queue: str = "default",
        meta: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> FakeJob:
        self._next_id += 1
        job = FakeJob(
            id=f"fake-{self._next_id:06d}",
            type=job_type,
            queue=queue,
            args=copy.deepcopy(args),
            meta=copy.deepcopy(meta or {}),
            options=copy.deepcopy(options or {}),
        )
        self.enqueued.append(job)
        return job

    def register_handler(
        self,
        job_type: str,
        handler: Callable[[FakeJob], None],
    ) -> None:
        self.handlers[job_type] = handler

    def clear(self) -> None:
        self.enqueued.clear()
        self.performed.clear()


class FakeTransport(Transport):
    """Producer-capable fake transport with isolated state."""

    def __init__(self, store: FakeStore | None = None) -> None:
        self.store = store or FakeStore()
        self.closed = False

    async def push(self, body: dict[str, Any]) -> Job:
        options = body.get("options", {})
        if not isinstance(options, dict):
            options = {}
        meta = body.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        args = body.get("args")
        if not isinstance(args, list):
            args = []
        fake_job = self.store.record_enqueue(
            job_type=str(body.get("type", "")),
            args=args,
            queue=str(options.get("queue", "default")),
            meta=meta,
            options=options,
        )
        return Job(
            id=fake_job.id,
            type=fake_job.type,
            state=JobState.AVAILABLE,
            args=copy.deepcopy(fake_job.args),
            queue=fake_job.queue,
            meta=copy.deepcopy(fake_job.meta),
            priority=int(options.get("priority", 0)),
            timeout_ms=options.get("timeout_ms"),
            tags=list(options.get("tags", [])),
        )

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        return [await self.push(job) for job in jobs]

    async def close(self) -> None:
        self.closed = True

    async def info(self, job_id: str) -> Job:
        return self._job(self._find(job_id))

    async def cancel(self, job_id: str) -> Job:
        job = self._find(job_id)
        job.state = "cancelled"
        return self._job(job)

    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]:
        selected: list[Job] = []
        for job in self.store.enqueued:
            if len(selected) >= count:
                break
            if job.queue not in queues or job.state not in {"available", "retryable"}:
                continue
            job.state = "active"
            job.attempt += 1
            selected.append(self._job(job))
        return selected

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        job = self._find(job_id)
        job.state = "completed"
        job.result = copy.deepcopy(result)
        return {"job_id": job_id, "state": job.state}

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        job = self._find(job_id)
        job.errors.append(copy.deepcopy(error))
        job.state = "retryable" if error.get("retryable", True) else "discarded"
        return {"job_id": job_id, "state": job.state}

    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        raise self._unsupported("worker heartbeat")

    async def list_queues(self) -> list[Queue]:
        raise self._unsupported("queue listing")

    async def queue_stats(self, queue_name: str) -> QueueStats:
        jobs = [job for job in self.store.enqueued if job.queue == queue_name]
        return QueueStats(
            queue=queue_name,
            status="active",
            available=sum(job.state == "available" for job in jobs),
            active=sum(job.state == "active" for job in jobs),
            scheduled=sum(job.state == "scheduled" for job in jobs),
            retryable=sum(job.state == "retryable" for job in jobs),
            discarded=sum(job.state == "discarded" for job in jobs),
        )

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        raise self._unsupported("queue pause")

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        raise self._unsupported("queue resume")

    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow:
        raise self._unsupported("workflow creation")

    async def get_workflow(self, workflow_id: str) -> Workflow:
        raise self._unsupported("workflow lookup")

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        raise self._unsupported("workflow cancellation")

    async def manifest(self) -> dict[str, Any]:
        raise self._unsupported("manifest")

    async def list_dead_letter_jobs(
        self,
        queue: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        raise self._unsupported("dead-letter listing")

    async def retry_dead_letter_job(self, job_id: str) -> Job:
        raise self._unsupported("dead-letter retry")

    async def delete_dead_letter_job(self, job_id: str) -> dict[str, Any]:
        raise self._unsupported("dead-letter deletion")

    async def list_cron_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        raise self._unsupported("cron listing")

    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]:
        raise self._unsupported("cron registration")

    async def unregister_cron_job(self, name: str) -> dict[str, Any]:
        raise self._unsupported("cron removal")

    async def list_schemas(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        raise self._unsupported("schema listing")

    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]:
        raise self._unsupported("schema registration")

    async def get_schema(self, uri: str) -> dict[str, Any]:
        raise self._unsupported("schema lookup")

    async def delete_schema(self, uri: str) -> dict[str, Any]:
        raise self._unsupported("schema deletion")

    async def progress(self, body: dict[str, Any]) -> dict[str, Any]:
        raise self._unsupported("progress reporting")

    async def get_progress(self, job_id: str) -> dict[str, Any]:
        raise self._unsupported("progress lookup")

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "transport": "fake"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise self._unsupported("generic requests")

    @staticmethod
    def _unsupported(capability: str) -> OJSCapabilityError:
        return OJSCapabilityError(
            f"FakeTransport does not implement {capability}; inject a transport "
            "that provides this capability."
        )

    def _find(self, job_id: str) -> FakeJob:
        for job in self.store.enqueued:
            if job.id == job_id:
                return job
        raise KeyError(job_id)

    @staticmethod
    def _job(job: FakeJob) -> Job:
        return Job(
            id=job.id,
            type=job.type,
            state=JobState(job.state),
            args=copy.deepcopy(job.args),
            queue=job.queue,
            meta=copy.deepcopy(job.meta),
            attempt=job.attempt,
            result=copy.deepcopy(job.result),
            errors=copy.deepcopy(job.errors),
        )


_ACTIVE_FAKE_TRANSPORT: ContextVar[FakeTransport | None] = ContextVar(
    "ojs_active_fake_transport",
    default=None,
)


def current_fake_transport() -> FakeTransport | None:
    return _ACTIVE_FAKE_TRANSPORT.get()


@contextmanager
def activate_fake_transport(
    transport: FakeTransport,
) -> Iterator[FakeTransport]:
    token: Token[FakeTransport | None] = _ACTIVE_FAKE_TRANSPORT.set(transport)
    try:
        yield transport
    finally:
        _ACTIVE_FAKE_TRANSPORT.reset(token)


__all__ = [
    "FakeJob",
    "FakeStore",
    "FakeTransport",
    "activate_fake_transport",
    "current_fake_transport",
]
