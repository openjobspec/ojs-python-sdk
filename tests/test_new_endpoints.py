"""Tests for manifest, dead-letter, cron, and schema endpoints."""

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


class TestManifest:
    async def test_manifest(self, client: ojs.Client) -> None:
        result = await client.manifest()
        assert result["ojs_version"] == "1.0"
        assert result["conformance_level"] == 3
        assert result["capabilities"]["dead_letter"] is True


class TestDeadLetter:
    async def test_list_dead_letter_jobs(self, client: ojs.Client) -> None:
        result = await client.list_dead_letter_jobs()
        assert result["jobs"] == []
        assert result["pagination"]["total"] == 0

    async def test_list_dead_letter_jobs_with_queue(self, client: ojs.Client) -> None:
        result = await client.list_dead_letter_jobs(queue="email", limit=10, offset=5)
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["offset"] == 5

    async def test_retry_dead_letter_job(self, client: ojs.Client) -> None:
        job = await client.retry_dead_letter_job("job-dead-001")
        assert job.id == "job-dead-001"
        assert job.state == ojs.JobState.AVAILABLE

    async def test_delete_dead_letter_job(self, client: ojs.Client) -> None:
        result = await client.delete_dead_letter_job("job-dead-001")
        assert result == {}


class TestCron:
    async def test_list_cron_jobs(self, client: ojs.Client) -> None:
        result = await client.list_cron_jobs()
        assert result["cron_jobs"] == []
        assert result["pagination"]["total"] == 0

    async def test_list_cron_jobs_with_pagination(self, client: ojs.Client) -> None:
        result = await client.list_cron_jobs(limit=25, offset=10)
        assert result["pagination"]["limit"] == 25
        assert result["pagination"]["offset"] == 10

    async def test_register_cron_job(self, client: ojs.Client) -> None:
        result = await client.register_cron_job(
            name="daily-cleanup",
            cron="0 0 * * *",
            type="system.cleanup",
            args=["stale"],
            queue="maintenance",
        )
        assert result["name"] == "daily-cleanup"
        assert result["cron"] == "0 0 * * *"
        assert result["status"] == "active"

    async def test_register_cron_job_minimal(self, client: ojs.Client) -> None:
        result = await client.register_cron_job(
            name="heartbeat",
            cron="*/5 * * * *",
            type="system.heartbeat",
        )
        assert result["name"] == "heartbeat"

    async def test_unregister_cron_job(self, client: ojs.Client) -> None:
        result = await client.unregister_cron_job("daily-cleanup")
        assert result == {}


class TestSchemas:
    async def test_list_schemas(self, client: ojs.Client) -> None:
        result = await client.list_schemas()
        assert result["schemas"] == []
        assert result["pagination"]["total"] == 0

    async def test_list_schemas_with_pagination(self, client: ojs.Client) -> None:
        result = await client.list_schemas(limit=20, offset=5)
        assert result["pagination"]["limit"] == 20
        assert result["pagination"]["offset"] == 5

    async def test_register_schema(self, client: ojs.Client) -> None:
        result = await client.register_schema(
            uri="ojs://schemas/email.send/v1",
            type="email.send",
            version="1.0",
            schema={"type": "array", "items": {"type": "string"}},
        )
        assert result["uri"] == "ojs://schemas/email.send/v1"
        assert result["type"] == "email.send"
        assert result["version"] == "1.0"

    async def test_get_schema(self, client: ojs.Client) -> None:
        result = await client.get_schema("ojs://schemas/email.send/v1")
        assert result["uri"] == "ojs://schemas/email.send/v1"

    async def test_delete_schema(self, client: ojs.Client) -> None:
        result = await client.delete_schema("ojs://schemas/email.send/v1")
        assert result == {}
