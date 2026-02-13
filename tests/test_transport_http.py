"""Tests for the HTTP transport layer."""

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

import ojs
from ojs.transport.http import _OJS_BASE_PATH, _OJS_CONTENT_TYPE, HTTPTransport
from ojs.workflow import WorkflowDefinition, WorkflowStep

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


class TestHTTPTransportInit:
    def test_strips_trailing_slash(self) -> None:
        t = HTTPTransport("http://example.com/")
        assert t._base_url == "http://example.com"

    def test_default_headers(self) -> None:
        t = HTTPTransport(BASE_URL)
        headers = dict(t._client.headers)
        assert headers["content-type"] == _OJS_CONTENT_TYPE
        assert headers["accept"] == _OJS_CONTENT_TYPE

    def test_custom_headers_merged(self) -> None:
        t = HTTPTransport(BASE_URL, headers={"X-Custom": "value"})
        headers = dict(t._client.headers)
        assert headers["x-custom"] == "value"
        assert headers["content-type"] == _OJS_CONTENT_TYPE

    def test_owns_client_when_not_injected(self) -> None:
        t = HTTPTransport(BASE_URL)
        assert t._owns_client is True

    def test_does_not_own_injected_client(self) -> None:
        client = httpx.AsyncClient()
        t = HTTPTransport(BASE_URL, client=client)
        assert t._owns_client is False

    def test_url_helper(self) -> None:
        t = HTTPTransport(BASE_URL)
        assert t._url("/jobs") == f"{_OJS_BASE_PATH}/jobs"


class TestPush:
    async def test_push_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/jobs",
            method="POST",
            json={"job": JOB_RESPONSE},
        )
        job = await transport.push(
            {"type": "email.send", "args": ["user@example.com"]}
        )
        assert job.id == JOB_RESPONSE["id"]
        assert job.type == "email.send"
        assert job.state == ojs.JobState.AVAILABLE

    async def test_push_sends_correct_body(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/jobs",
            method="POST",
            json={"job": JOB_RESPONSE},
        )
        await transport.push({"type": "email.send", "args": ["a@b.com"]})
        request = httpx_mock.get_request()
        assert request is not None
        body = json.loads(request.content)
        assert body["type"] == "email.send"
        assert body["args"] == ["a@b.com"]


class TestPushBatch:
    async def test_push_batch(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/jobs/batch",
            method="POST",
            json={
                "jobs": [
                    JOB_RESPONSE,
                    {**JOB_RESPONSE, "id": "019463ab-0002"},
                ]
            },
        )
        jobs = await transport.push_batch([
            {"type": "email.send", "args": ["a@b.com"]},
            {"type": "email.send", "args": ["c@d.com"]},
        ])
        assert len(jobs) == 2
        assert jobs[0].id == JOB_RESPONSE["id"]
        assert jobs[1].id == "019463ab-0002"


class TestInfo:
    async def test_get_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        job_id = JOB_RESPONSE["id"]
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/jobs/{job_id}",
            method="GET",
            json={"job": JOB_RESPONSE},
        )
        job = await transport.info(job_id)
        assert job.id == job_id
        assert job.type == "email.send"


class TestCancel:
    async def test_cancel_job(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        job_id = JOB_RESPONSE["id"]
        cancelled = {**JOB_RESPONSE, "state": "cancelled"}
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/jobs/{job_id}",
            method="DELETE",
            json={"job": cancelled},
        )
        job = await transport.cancel(job_id)
        assert job.state == ojs.JobState.CANCELLED


class TestFetch:
    async def test_fetch_jobs(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        active_job = {**JOB_RESPONSE, "state": "active", "attempt": 1}
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/fetch",
            method="POST",
            json={"jobs": [active_job]},
        )
        jobs = await transport.fetch(queues=["default"], worker_id="w1")
        assert len(jobs) == 1
        assert jobs[0].state == ojs.JobState.ACTIVE

    async def test_fetch_empty(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/fetch",
            method="POST",
            json={"jobs": []},
        )
        jobs = await transport.fetch(queues=["default"])
        assert jobs == []

    async def test_fetch_sends_worker_id(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/fetch",
            method="POST",
            json={"jobs": []},
        )
        await transport.fetch(
            queues=["email"],
            worker_id="worker_abc",
            visibility_timeout_ms=60000,
        )
        request = httpx_mock.get_request()
        assert request is not None
        body = json.loads(request.content)
        assert body["worker_id"] == "worker_abc"
        assert body["queues"] == ["email"]
        assert body["visibility_timeout_ms"] == 60000


class TestAck:
    async def test_ack_without_result(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/ack",
            method="POST",
            json={"state": "completed"},
        )
        resp = await transport.ack("job-123")
        assert resp["state"] == "completed"

    async def test_ack_with_result(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/ack",
            method="POST",
            json={"state": "completed"},
        )
        await transport.ack("job-123", result={"sent": True})
        request = httpx_mock.get_request()
        assert request is not None
        body = json.loads(request.content)
        assert body["job_id"] == "job-123"
        assert body["result"] == {"sent": True}


class TestNack:
    async def test_nack(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/nack",
            method="POST",
            json={"state": "retryable"},
        )
        error = {
            "code": "handler_error",
            "message": "boom",
            "retryable": True,
        }
        resp = await transport.nack("job-123", error)
        assert resp["state"] == "retryable"


class TestHeartbeat:
    async def test_heartbeat(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workers/heartbeat",
            method="POST",
            json={"state": "running", "jobs_extended": 2},
        )
        resp = await transport.heartbeat(
            worker_id="w1",
            active_jobs=["j1", "j2"],
            visibility_timeout_ms=30000,
        )
        assert resp["state"] == "running"
        assert resp["jobs_extended"] == 2


class TestQueueOperations:
    async def test_list_queues(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/queues",
            method="GET",
            json={
                "queues": [
                    {"name": "default", "status": "active"},
                    {"name": "email", "status": "paused"},
                ]
            },
        )
        queues = await transport.list_queues()
        assert len(queues) == 2
        assert queues[0].name == "default"
        assert queues[1].status == "paused"

    async def test_queue_stats(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/queues/default/stats",
            method="GET",
            json={
                "queue": "default",
                "status": "active",
                "stats": {
                    "available": 10,
                    "active": 3,
                    "completed_last_hour": 50,
                },
            },
        )
        stats = await transport.queue_stats("default")
        assert stats.queue == "default"
        assert stats.available == 10
        assert stats.active == 3
        assert stats.completed_last_hour == 50

    async def test_pause_queue(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/queues/email/pause",
            method="POST",
            json={"status": "paused"},
        )
        resp = await transport.pause_queue("email")
        assert resp["status"] == "paused"

    async def test_resume_queue(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/queues/email/resume",
            method="POST",
            json={"status": "active"},
        )
        resp = await transport.resume_queue("email")
        assert resp["status"] == "active"


class TestWorkflowOperations:
    async def test_create_workflow(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workflows",
            method="POST",
            json={
                "workflow": {
                    "id": "wf-001",
                    "name": "my-chain",
                    "state": "running",
                    "steps": [
                        {
                            "id": "step-1",
                            "type": "email.send",
                            "state": "active",
                        },
                        {
                            "id": "step-2",
                            "type": "notify",
                            "state": "pending",
                            "depends_on": ["step-1"],
                        },
                    ],
                }
            },
        )
        definition = WorkflowDefinition(
            name="my-chain",
            steps=[
                WorkflowStep(
                    id="step-1", type="email.send", args=["a@b.com"]
                ),
                WorkflowStep(
                    id="step-2",
                    type="notify",
                    args=[],
                    depends_on=["step-1"],
                ),
            ],
        )
        wf = await transport.create_workflow(definition)
        assert wf.id == "wf-001"
        assert wf.name == "my-chain"
        assert len(wf.steps) == 2

    async def test_get_workflow(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workflows/wf-001",
            method="GET",
            json={
                "workflow": {
                    "id": "wf-001",
                    "name": "test",
                    "state": "completed",
                    "steps": [],
                }
            },
        )
        wf = await transport.get_workflow("wf-001")
        assert wf.state == "completed"

    async def test_cancel_workflow(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/workflows/wf-001",
            method="DELETE",
            json={"state": "cancelled"},
        )
        resp = await transport.cancel_workflow("wf-001")
        assert resp["state"] == "cancelled"


class TestHealth:
    async def test_health_check(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/health",
            method="GET",
            json={"status": "ok"},
        )
        resp = await transport.health()
        assert resp["status"] == "ok"


class TestErrorHandling:
    async def test_connection_error(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        with pytest.raises(ojs.OJSConnectionError, match="Failed to connect"):
            await transport.push({"type": "test", "args": []})

    async def test_timeout_error(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_exception(httpx.ReadTimeout("read timeout"))
        with pytest.raises(ojs.OJSTimeoutError, match="timed out"):
            await transport.push({"type": "test", "args": []})

    async def test_404_raises_not_found(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            status_code=404,
            json={
                "error": {
                    "code": "not_found",
                    "message": "Job not found",
                    "retryable": False,
                }
            },
        )
        with pytest.raises(ojs.JobNotFoundError):
            await transport.info("nonexistent-id")

    async def test_409_raises_duplicate(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            status_code=409,
            json={
                "error": {
                    "code": "duplicate",
                    "message": "Already exists",
                    "retryable": False,
                }
            },
        )
        with pytest.raises(ojs.DuplicateJobError):
            await transport.push({"type": "test", "args": []})

    async def test_429_raises_rate_limited(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            status_code=429,
            json={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests",
                    "retryable": True,
                }
            },
            headers={"retry-after": "30"},
        )
        with pytest.raises(ojs.RateLimitedError) as exc_info:
            await transport.push({"type": "test", "args": []})
        assert exc_info.value.retry_after == 30.0

    async def test_500_raises_api_error(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            status_code=500,
            json={
                "error": {
                    "code": "internal",
                    "message": "Server error",
                    "retryable": True,
                }
            },
        )
        with pytest.raises(ojs.OJSAPIError) as exc_info:
            await transport.health()
        assert exc_info.value.status_code == 500

    async def test_204_returns_empty_dict(
        self, httpx_mock: HTTPXMock, transport: HTTPTransport
    ) -> None:
        httpx_mock.add_response(
            url=f"{BASE_URL}{_OJS_BASE_PATH}/queues/email/pause",
            method="POST",
            status_code=204,
        )
        resp = await transport.pause_queue("email")
        assert resp == {}


class TestClose:
    async def test_close_owned_client(self) -> None:
        transport = HTTPTransport(BASE_URL)
        assert transport._owns_client is True
        await transport.close()

    async def test_close_injected_client_not_closed(self) -> None:
        client = httpx.AsyncClient()
        transport = HTTPTransport(BASE_URL, client=client)
        await transport.close()
        assert not client.is_closed
        await client.aclose()
