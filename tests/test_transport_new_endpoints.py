"""Tests for HTTP transport: manifest, dead-letter, cron, and schema endpoints."""

import json

import pytest
from pytest_httpx import HTTPXMock

import ojs
from ojs.transport.http import _OJS_BASE_PATH, HTTPTransport

BASE_URL = "http://localhost:8080"

JOB_RESPONSE = {
    "id": "019463ab-1234-7000-8000-000000000001",
    "type": "email.send",
    "state": "available",
    "args": ["user@example.com", "welcome"],
    "queue": "default",
    "priority": 0,
    "attempt": 0,
    "max_attempts": 3,
}


@pytest.fixture
def transport() -> HTTPTransport:
    return HTTPTransport(BASE_URL)


class TestManifest:
    async def test_manifest(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}/ojs/manifest",
            method="GET",
            json={
                "ojs_version": "1.0",
                "conformance_level": 3,
                "capabilities": {"dead_letter": True},
            },
        )
        result = await transport.manifest()
        assert result["ojs_version"] == "1.0"
        assert result["conformance_level"] == 3

    async def test_manifest_uses_raw_path(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}/ojs/manifest",
            method="GET",
            json={"ojs_version": "1.0"},
        )
        await transport.manifest()
        request = httpx_mock.get_request()
        assert request is not None
        assert str(request.url).startswith(f"{BASE_URL}/ojs/manifest")


class TestDeadLetterTransport:
    async def test_list_dead_letter_jobs(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/dead-letter?limit=50&offset=0",
            method="GET",
            json={
                "jobs": [
                    {**JOB_RESPONSE, "state": "discarded"},
                ],
                "pagination": {"total": 1, "limit": 50, "offset": 0},
            },
        )
        result = await transport.list_dead_letter_jobs()
        assert len(result["jobs"]) == 1
        assert result["pagination"]["total"] == 1

    async def test_list_dead_letter_jobs_with_queue(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/dead-letter?limit=10&offset=5&queue=email",
            method="GET",
            json={"jobs": [], "pagination": {"total": 0, "limit": 10, "offset": 5}},
        )
        result = await transport.list_dead_letter_jobs(queue="email", limit=10, offset=5)
        assert result["jobs"] == []

    async def test_retry_dead_letter_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        job_id = JOB_RESPONSE["id"]
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/dead-letter/{job_id}/retry",
            method="POST",
            json={"job": {**JOB_RESPONSE, "state": "available"}},
        )
        job = await transport.retry_dead_letter_job(job_id)
        assert job.id == job_id
        assert job.state == ojs.JobState.AVAILABLE

    async def test_delete_dead_letter_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        job_id = JOB_RESPONSE["id"]
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/dead-letter/{job_id}",
            method="DELETE",
            status_code=204,
        )
        result = await transport.delete_dead_letter_job(job_id)
        assert result == {}


class TestCronTransport:
    async def test_list_cron_jobs(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/cron?limit=50&offset=0",
            method="GET",
            json={
                "cron_jobs": [
                    {
                        "name": "daily-cleanup",
                        "cron": "0 0 * * *",
                        "type": "system.cleanup",
                        "status": "active",
                    },
                ],
                "pagination": {"total": 1, "limit": 50, "offset": 0},
            },
        )
        result = await transport.list_cron_jobs()
        assert len(result["cron_jobs"]) == 1
        assert result["cron_jobs"][0]["name"] == "daily-cleanup"

    async def test_register_cron_job(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/cron",
            method="POST",
            json={
                "name": "daily-cleanup",
                "cron": "0 0 * * *",
                "type": "system.cleanup",
                "status": "active",
            },
        )
        body = {
            "name": "daily-cleanup",
            "cron": "0 0 * * *",
            "type": "system.cleanup",
            "args": [],
        }
        result = await transport.register_cron_job(body)
        assert result["name"] == "daily-cleanup"

        request = httpx_mock.get_request()
        assert request is not None
        sent = json.loads(request.content)
        assert sent["name"] == "daily-cleanup"
        assert sent["cron"] == "0 0 * * *"

    async def test_unregister_cron_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/cron/daily-cleanup",
            method="DELETE",
            status_code=204,
        )
        result = await transport.unregister_cron_job("daily-cleanup")
        assert result == {}


class TestSchemaTransport:
    async def test_list_schemas(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/schemas?limit=50&offset=0",
            method="GET",
            json={
                "schemas": [
                    {"uri": "ojs://email.send/v1", "type": "email.send", "version": "1.0"},
                ],
                "pagination": {"total": 1, "limit": 50, "offset": 0},
            },
        )
        result = await transport.list_schemas()
        assert len(result["schemas"]) == 1

    async def test_register_schema(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/schemas",
            method="POST",
            json={
                "uri": "ojs://email.send/v1",
                "type": "email.send",
                "version": "1.0",
                "schema": {"type": "array"},
            },
        )
        body = {
            "uri": "ojs://email.send/v1",
            "type": "email.send",
            "version": "1.0",
            "schema": {"type": "array"},
        }
        result = await transport.register_schema(body)
        assert result["uri"] == "ojs://email.send/v1"

        request = httpx_mock.get_request()
        assert request is not None
        sent = json.loads(request.content)
        assert sent["uri"] == "ojs://email.send/v1"
        assert sent["schema"] == {"type": "array"}

    async def test_get_schema(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        # URI is URL-encoded: ojs://email.send/v1 → ojs%3A%2F%2Femail.send%2Fv1
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/schemas/ojs%3A%2F%2Femail.send%2Fv1",
            method="GET",
            json={
                "uri": "ojs://email.send/v1",
                "type": "email.send",
                "version": "1.0",
                "schema": {"type": "array"},
            },
        )
        result = await transport.get_schema("ojs://email.send/v1")
        assert result["uri"] == "ojs://email.send/v1"

    async def test_delete_schema(self, httpx_mock: HTTPXMock, transport: HTTPTransport) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/schemas/ojs%3A%2F%2Femail.send%2Fv1",
            method="DELETE",
            status_code=204,
        )
        result = await transport.delete_schema("ojs://email.send/v1")
        assert result == {}

