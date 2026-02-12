"""HTTP transport for OJS using httpx.

Implements the OJS HTTP/REST Protocol Binding (Layer 3).
"""

from __future__ import annotations

from typing import Any

import httpx

from ojs.errors import OJSConnectionError, OJSTimeoutError, raise_for_error
from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.transport.base import Transport
from ojs.workflow import Workflow, WorkflowDefinition

_OJS_CONTENT_TYPE = "application/openjobspec+json"
_OJS_BASE_PATH = "/ojs/v1"


class HTTPTransport(Transport):
    """HTTP transport using httpx.AsyncClient.

    Implements the OJS HTTP binding specification.

    Args:
        base_url: The OJS server base URL (e.g., "http://localhost:8080").
        timeout: Request timeout in seconds. Default: 30.
        headers: Additional HTTP headers to include in all requests.
        client: Optional pre-configured httpx.AsyncClient to use.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        default_headers = {
            "Content-Type": _OJS_CONTENT_TYPE,
            "Accept": _OJS_CONTENT_TYPE,
        }
        if headers:
            default_headers.update(headers)

        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=default_headers,
        )

    def _url(self, path: str) -> str:
        return f"{_OJS_BASE_PATH}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request and handle errors."""
        try:
            response = await self._client.request(
                method,
                self._url(path),
                json=json,
                params=params,
            )
        except httpx.ConnectError as e:
            raise OJSConnectionError(
                f"Failed to connect to OJS server at {self._base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise OJSTimeoutError(
                f"Request to OJS server timed out: {e}"
            ) from e

        if response.status_code >= 400:
            body = response.json()
            headers = dict(response.headers)
            raise_for_error(response.status_code, body, headers)

        if response.status_code == 204:
            return {}
        result: dict[str, Any] = response.json()
        return result

    # --- Job Operations ---

    async def push(self, body: dict[str, Any]) -> Job:
        data = await self._request("POST", "/jobs", json=body)
        return Job.from_dict(data["job"])

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        data = await self._request("POST", "/jobs/batch", json={"jobs": jobs})
        return [Job.from_dict(j) for j in data["jobs"]]

    async def info(self, job_id: str) -> Job:
        data = await self._request("GET", f"/jobs/{job_id}")
        return Job.from_dict(data["job"])

    async def cancel(self, job_id: str) -> Job:
        data = await self._request("DELETE", f"/jobs/{job_id}")
        return Job.from_dict(data["job"])

    # --- Worker Operations ---

    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]:
        body: dict[str, Any] = {
            "queues": queues,
            "count": count,
            "visibility_timeout_ms": visibility_timeout_ms,
        }
        if worker_id:
            body["worker_id"] = worker_id
        data = await self._request("POST", "/workers/fetch", json=body)
        return [Job.from_dict(j) for j in data.get("jobs", [])]

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        body: dict[str, Any] = {"job_id": job_id}
        if result is not None:
            body["result"] = result
        return await self._request("POST", "/workers/ack", json=body)

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST", "/workers/nack", json={"job_id": job_id, "error": error}
        )

    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"worker_id": worker_id}
        if active_jobs is not None:
            body["active_jobs"] = active_jobs
        if visibility_timeout_ms is not None:
            body["visibility_timeout_ms"] = visibility_timeout_ms
        return await self._request("POST", "/workers/heartbeat", json=body)

    # --- Queue Operations ---

    async def list_queues(self) -> list[Queue]:
        data = await self._request("GET", "/queues")
        return [Queue.from_dict(q) for q in data.get("queues", [])]

    async def queue_stats(self, queue_name: str) -> QueueStats:
        data = await self._request("GET", f"/queues/{queue_name}/stats")
        return QueueStats.from_dict(data)

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        return await self._request("POST", f"/queues/{queue_name}/pause")

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        return await self._request("POST", f"/queues/{queue_name}/resume")

    # --- Workflow Operations ---

    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow:
        data = await self._request(
            "POST", "/workflows", json=definition.to_dict()
        )
        return Workflow.from_dict(data["workflow"])

    async def get_workflow(self, workflow_id: str) -> Workflow:
        data = await self._request("GET", f"/workflows/{workflow_id}")
        return Workflow.from_dict(data["workflow"])

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/workflows/{workflow_id}")

    # --- Lifecycle ---

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
