"""Integration tests against a live OJS server with Redis backend.

These tests require a running OJS server at the URL specified by
the OJS_SERVER_URL environment variable (default: http://localhost:8080).

Run with:
    OJS_SERVER_URL=http://localhost:8080 pytest tests/integration/ -v
"""

from __future__ import annotations

import os

import pytest

import ojs

OJS_SERVER_URL = os.environ.get("OJS_SERVER_URL", "http://localhost:8080")

# Skip all tests if the OJS server is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("OJS_INTEGRATION_TESTS") != "1",
    reason="Set OJS_INTEGRATION_TESTS=1 and OJS_SERVER_URL to run integration tests",
)


@pytest.fixture
async def client():
    async with ojs.Client(OJS_SERVER_URL) as c:
        yield c


class TestHealthCheck:
    async def test_server_healthy(self, client: ojs.Client) -> None:
        result = await client.health()
        assert result["status"] == "ok"


class TestEnqueueAndRetrieve:
    async def test_enqueue_and_get_job(self, client: ojs.Client) -> None:
        job = await client.enqueue(
            "test.echo",
            ["hello", "world"],
            queue="test-integration",
        )

        assert job.id is not None
        assert job.type == "test.echo"
        assert job.state in (ojs.JobState.AVAILABLE, ojs.JobState.SCHEDULED)
        assert job.args == ["hello", "world"]

        # Retrieve the job
        fetched = await client.get_job(job.id)
        assert fetched.id == job.id
        assert fetched.type == "test.echo"

    async def test_enqueue_with_retry_policy(self, client: ojs.Client) -> None:
        job = await client.enqueue(
            "test.echo",
            ["retry-test"],
            retry=ojs.RetryPolicy(
                max_attempts=5,
                initial_interval="PT2S",
                backoff_coefficient=3.0,
            ),
        )
        assert job.id is not None

    async def test_enqueue_batch(self, client: ojs.Client) -> None:
        jobs = await client.enqueue_batch([
            ojs.JobRequest(type="test.echo", args=["batch-1"], queue="test-integration"),
            ojs.JobRequest(type="test.echo", args=["batch-2"], queue="test-integration"),
            ojs.JobRequest(type="test.echo", args=["batch-3"], queue="test-integration"),
        ])
        assert len(jobs) == 3
        for j in jobs:
            assert j.id is not None


class TestCancelJob:
    async def test_cancel_available_job(self, client: ojs.Client) -> None:
        job = await client.enqueue("test.echo", ["to-cancel"], queue="test-integration")
        cancelled = await client.cancel_job(job.id)
        assert cancelled.state == ojs.JobState.CANCELLED


class TestQueues:
    async def test_list_queues(self, client: ojs.Client) -> None:
        queues = await client.list_queues()
        assert isinstance(queues, list)
        queue_names = [q.name for q in queues]
        assert "default" in queue_names


class TestWorkflow:
    async def test_create_chain_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.chain(
                "integration-test-chain",
                [
                    ojs.JobRequest(type="test.echo", args=["step1"]),
                    ojs.JobRequest(type="test.echo", args=["step2"]),
                ],
            )
        )
        assert wf.id is not None
        assert wf.state in ("running", "active")

        # Check workflow status
        status = await client.get_workflow(wf.id)
        assert status.id == wf.id
