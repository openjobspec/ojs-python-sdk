"""Tests for the OJS Client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

import ojs
from ojs.transport.base import Transport


class FakeTransport(Transport):
    """In-memory fake transport for testing."""

    def __init__(self) -> None:
        self.pushed: list[dict[str, Any]] = []
        self.push_response: dict[str, Any] = {
            "id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
            "type": "test.echo",
            "state": "available",
            "args": [],
            "queue": "default",
            "created_at": "2026-02-12T10:00:00.000Z",
            "enqueued_at": "2026-02-12T10:00:00.123Z",
        }

    async def push(self, body: dict[str, Any]) -> ojs.Job:
        self.pushed.append(body)
        response = {**self.push_response, **{"type": body["type"], "args": body["args"]}}
        return ojs.Job.from_dict(response)

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[ojs.Job]:
        self.pushed.extend(jobs)
        return [
            ojs.Job.from_dict({
                **self.push_response,
                "id": f"019539a4-b68c-7def-8000-{i:012x}",
                "type": j["type"],
                "args": j["args"],
            })
            for i, j in enumerate(jobs)
        ]

    async def info(self, job_id: str) -> ojs.Job:
        return ojs.Job.from_dict({**self.push_response, "id": job_id, "state": "completed"})

    async def cancel(self, job_id: str) -> ojs.Job:
        return ojs.Job.from_dict({**self.push_response, "id": job_id, "state": "cancelled"})

    async def fetch(self, queues, count=1, worker_id=None, visibility_timeout_ms=30000):
        return []

    async def ack(self, job_id, result=None):
        return {"acknowledged": True, "job_id": job_id, "state": "completed"}

    async def nack(self, job_id, error):
        return {"job_id": job_id, "state": "retryable"}

    async def heartbeat(self, worker_id, active_jobs=None, visibility_timeout_ms=None):
        return {"state": "running", "jobs_extended": active_jobs or []}

    async def list_queues(self):
        return [ojs.Queue(name="default", status="active")]

    async def queue_stats(self, queue_name):
        return ojs.QueueStats(queue=queue_name, status="active")

    async def pause_queue(self, queue_name):
        return {"queue": queue_name, "status": "paused"}

    async def resume_queue(self, queue_name):
        return {"queue": queue_name, "status": "active"}

    async def create_workflow(self, definition):
        return ojs.Workflow(id="wf-123", name=definition.name, state="running")

    async def get_workflow(self, workflow_id):
        return ojs.Workflow(id=workflow_id, name="test", state="running")

    async def cancel_workflow(self, workflow_id):
        return {"workflow": {"id": workflow_id, "state": "cancelled"}}

    async def health(self):
        return {"status": "ok"}

    async def close(self):
        pass


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def client(transport: FakeTransport) -> ojs.Client:
    return ojs.Client("http://localhost:8080", transport=transport)


class TestEnqueue:
    async def test_enqueue_simple(self, client: ojs.Client, transport: FakeTransport) -> None:
        job = await client.enqueue("email.send", ["user@example.com", "welcome"])

        assert job.type == "email.send"
        assert job.args == ["user@example.com", "welcome"]
        assert job.state == ojs.JobState.AVAILABLE
        assert len(transport.pushed) == 1
        assert transport.pushed[0]["type"] == "email.send"

    async def test_enqueue_with_options(self, client: ojs.Client, transport: FakeTransport) -> None:
        job = await client.enqueue(
            "email.send",
            ["user@example.com"],
            queue="email",
            retry=ojs.RetryPolicy(max_attempts=5),
            tags=["onboarding"],
        )

        assert job.type == "email.send"
        body = transport.pushed[0]
        assert body["options"]["queue"] == "email"
        assert body["options"]["retry"]["max_attempts"] == 5
        assert body["options"]["tags"] == ["onboarding"]

    async def test_enqueue_empty_args(self, client: ojs.Client) -> None:
        job = await client.enqueue("system.health_check")
        assert job.args == []

    async def test_enqueue_batch(self, client: ojs.Client, transport: FakeTransport) -> None:
        jobs = await client.enqueue_batch([
            ojs.JobRequest(type="email.send", args=["a@b.com"]),
            ojs.JobRequest(type="email.send", args=["c@d.com"]),
        ])

        assert len(jobs) == 2
        assert len(transport.pushed) == 2


class TestEnqueueMiddleware:
    async def test_middleware_modifies_request(self, transport: FakeTransport) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def add_trace(request, next):
            request.meta = request.meta or {}
            request.meta["trace_id"] = "abc123"
            return await next(request)

        job = await client.enqueue("test.echo", ["hello"])

        body = transport.pushed[0]
        assert body["meta"]["trace_id"] == "abc123"


class TestJobOperations:
    async def test_get_job(self, client: ojs.Client) -> None:
        job = await client.get_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
        assert job.id == "019539a4-b68c-7def-8000-1a2b3c4d5e6f"
        assert job.state == ojs.JobState.COMPLETED

    async def test_cancel_job(self, client: ojs.Client) -> None:
        job = await client.cancel_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
        assert job.state == ojs.JobState.CANCELLED


class TestWorkflow:
    async def test_create_chain_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.chain("test-chain", [
                ojs.JobRequest(type="step.one", args=["a"]),
                ojs.JobRequest(type="step.two", args=["b"]),
            ])
        )
        assert wf.name == "test-chain"
        assert wf.state == "running"

    async def test_create_group_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.group("test-group", [
                ojs.JobRequest(type="task.a", args=[1]),
                ojs.JobRequest(type="task.b", args=[2]),
            ])
        )
        assert wf.name == "test-group"


class TestContextManager:
    async def test_async_context_manager(self, transport: FakeTransport) -> None:
        async with ojs.Client("http://localhost:8080", transport=transport) as client:
            job = await client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"

    async def test_health(self, client: ojs.Client) -> None:
        result = await client.health()
        assert result["status"] == "ok"
