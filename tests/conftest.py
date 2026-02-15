"""Shared test fixtures for the OJS test suite."""

from __future__ import annotations

from typing import Any

import ojs
from ojs.job import Job
from ojs.transport.base import Transport


class FakeTransport(Transport):
    """In-memory fake transport for testing.

    Tracks all pushed/acked/nacked operations for assertion.
    Configurable fetch responses via set_fetch_jobs().
    """

    def __init__(self) -> None:
        self.pushed: list[dict[str, Any]] = []
        self.acked: list[dict[str, Any]] = []
        self.nacked: list[dict[str, Any]] = []
        self.fetched_count = 0
        self._fetch_jobs: list[Job] = []
        self._heartbeat_responses: list[dict[str, Any]] = []
        self._fetch_error: Exception | None = None
        self.push_response: dict[str, Any] = {
            "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
            "type": "test.echo",
            "state": "available",
            "args": [],
            "queue": "default",
            "created_at": "2026-02-12T10:00:00.000Z",
            "enqueued_at": "2026-02-12T10:00:00.123Z",
        }

    def set_fetch_jobs(self, jobs: list[Job]) -> None:
        self._fetch_jobs = list(jobs)

    def set_fetch_error(self, error: Exception) -> None:
        self._fetch_error = error

    def set_heartbeat_responses(self, responses: list[dict[str, Any]]) -> None:
        self._heartbeat_responses = list(responses)

    async def push(self, body: dict[str, Any]) -> Job:
        self.pushed.append(body)
        response = {
            **self.push_response,
            "type": body["type"],
            "args": body["args"],
        }
        return Job.from_dict(response)

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        self.pushed.extend(jobs)
        return [
            Job.from_dict(
                {
                    **self.push_response,
                    "id": f"019539a4-b68c-7def-8000-{i:012x}",
                    "type": j["type"],
                    "args": j["args"],
                }
            )
            for i, j in enumerate(jobs)
        ]

    async def info(self, job_id: str) -> Job:
        return Job.from_dict(
            {
                **self.push_response,
                "id": job_id,
                "state": "completed",
            }
        )

    async def cancel(self, job_id: str) -> Job:
        return Job.from_dict(
            {
                **self.push_response,
                "id": job_id,
                "state": "cancelled",
            }
        )

    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]:
        self.fetched_count += 1
        if self._fetch_error is not None:
            err = self._fetch_error
            self._fetch_error = None
            raise err
        if self._fetch_jobs:
            jobs = self._fetch_jobs[:count]
            self._fetch_jobs = self._fetch_jobs[count:]
            return jobs
        return []

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        self.acked.append({"job_id": job_id, "result": result})
        return {"acknowledged": True, "job_id": job_id, "state": "completed"}

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        self.nacked.append({"job_id": job_id, "error": error})
        return {"job_id": job_id, "state": "retryable"}

    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if self._heartbeat_responses:
            return self._heartbeat_responses.pop(0)
        return {"state": "running", "jobs_extended": active_jobs or []}

    async def list_queues(self) -> list[ojs.Queue]:
        return [ojs.Queue(name="default", status="active")]

    async def queue_stats(self, queue_name: str) -> ojs.QueueStats:
        return ojs.QueueStats(queue=queue_name, status="active")

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        return {"queue": queue_name, "status": "paused"}

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        return {"queue": queue_name, "status": "active"}

    async def create_workflow(self, definition: Any) -> ojs.Workflow:
        return ojs.Workflow(id="wf-123", name=definition.name, state="running")

    async def get_workflow(self, workflow_id: str) -> ojs.Workflow:
        return ojs.Workflow(id=workflow_id, name="test", state="running")

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        return {"workflow": {"id": workflow_id, "state": "cancelled"}}

    async def health(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def close(self) -> None:
        pass
