"""Tests for the OJS Client."""

from __future__ import annotations

import pytest

import ojs
from tests.conftest import FakeTransport


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
        jobs = await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["a@b.com"]),
                ojs.JobRequest(type="email.send", args=["c@d.com"]),
            ]
        )

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

        await client.enqueue("test.echo", ["hello"])

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
            ojs.chain(
                "test-chain",
                [
                    ojs.JobRequest(type="step.one", args=["a"]),
                    ojs.JobRequest(type="step.two", args=["b"]),
                ],
            )
        )
        assert wf.name == "test-chain"
        assert wf.state == "running"

    async def test_create_group_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.group(
                "test-group",
                [
                    ojs.JobRequest(type="task.a", args=[1]),
                    ojs.JobRequest(type="task.b", args=[2]),
                ],
            )
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


class TestSyncClient:
    def test_sync_enqueue(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient.__new__(ojs.SyncClient)
        client._client = ojs.Client("http://localhost:8080", transport=transport)
        client._loop = None
        try:
            job = client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"
        finally:
            client.close()

    def test_sync_get_job(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient.__new__(ojs.SyncClient)
        client._client = ojs.Client("http://localhost:8080", transport=transport)
        client._loop = None
        try:
            job = client.get_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
            assert job.state.value == "completed"
        finally:
            client.close()

    def test_sync_list_queues(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient.__new__(ojs.SyncClient)
        client._client = ojs.Client("http://localhost:8080", transport=transport)
        client._loop = None
        try:
            queues = client.list_queues()
            assert len(queues) == 1
            assert queues[0].name == "default"
        finally:
            client.close()

    def test_sync_queue_stats(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient.__new__(ojs.SyncClient)
        client._client = ojs.Client("http://localhost:8080", transport=transport)
        client._loop = None
        try:
            stats = client.queue_stats("default")
            assert stats.queue == "default"
        finally:
            client.close()

    def test_sync_context_manager(self, transport: FakeTransport) -> None:
        with ojs.SyncClient.__new__(ojs.SyncClient) as client:
            client._client = ojs.Client("http://localhost:8080", transport=transport)
            client._loop = None
            job = client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"
