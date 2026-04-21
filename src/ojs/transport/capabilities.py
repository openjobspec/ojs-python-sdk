"""Narrow transport capabilities used by OJS actors."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.workflow import Workflow, WorkflowDefinition


@runtime_checkable
class ProducerTransport(Protocol):
    """Transport operations used to produce and inspect jobs."""

    async def push(self, body: dict[str, Any]) -> Job: ...

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]: ...

    async def info(self, job_id: str) -> Job: ...

    async def cancel(self, job_id: str) -> Job: ...


@runtime_checkable
class WorkerTransport(Protocol):
    """Transport operations used by a worker runtime."""

    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]: ...

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]: ...

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]: ...

    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class WorkflowTransport(Protocol):
    """Transport operations used to manage workflows."""

    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow: ...

    async def get_workflow(self, workflow_id: str) -> Workflow: ...

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]: ...


@runtime_checkable
class CheckpointTransport(Protocol):
    """Generic endpoint capability used by durable checkpoints."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class ProgressTransport(Protocol):
    """Transport capability for reporting handler progress."""

    async def progress(self, body: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class AdministrationTransport(Protocol):
    """Queue, manifest, dead-letter, cron, schema, and lifecycle operations."""

    async def list_queues(self) -> list[Queue]: ...

    async def queue_stats(self, queue_name: str) -> QueueStats: ...

    async def pause_queue(self, queue_name: str) -> dict[str, Any]: ...

    async def resume_queue(self, queue_name: str) -> dict[str, Any]: ...

    async def manifest(self) -> dict[str, Any]: ...

    async def list_dead_letter_jobs(
        self,
        queue: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    async def retry_dead_letter_job(self, job_id: str) -> Job: ...

    async def delete_dead_letter_job(self, job_id: str) -> dict[str, Any]: ...

    async def list_cron_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]: ...

    async def unregister_cron_job(self, name: str) -> dict[str, Any]: ...

    async def list_schemas(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]: ...

    async def get_schema(self, uri: str) -> dict[str, Any]: ...

    async def delete_schema(self, uri: str) -> dict[str, Any]: ...

    async def health(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...
