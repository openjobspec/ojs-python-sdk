"""HTTP transport for OJS using httpx.

Implements the OJS HTTP/REST Protocol Binding (Layer 3).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from ojs.errors import OJSConnectionError, OJSTimeoutError, raise_for_error
from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.transport.base import Transport
from ojs.transport.rate_limiter import RetryConfig, sleep_before_retry
from ojs.workflow import Workflow, WorkflowDefinition

_OJS_CONTENT_TYPE = "application/openjobspec+json"
_OJS_BASE_PATH = "/ojs/v1"
_OJS_VERSION = "1.0"

logger = logging.getLogger("ojs.transport.http")


class HTTPTransport(Transport):
    """HTTP transport using httpx.AsyncClient.

    Implements the OJS HTTP binding specification.

    Args:
        base_url: The OJS server base URL (e.g., "http://localhost:8080").
        timeout: Request timeout in seconds. Default: 30.
        headers: Additional HTTP headers to include in all requests.
        client: Optional pre-configured httpx.AsyncClient to use.
        retry_config: Configuration for automatic 429 rate-limit retries.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._retry_config = retry_config or RetryConfig()
        default_headers = {
            "Content-Type": _OJS_CONTENT_TYPE,
            "Accept": _OJS_CONTENT_TYPE,
            "OJS-Version": _OJS_VERSION,
        }
        if headers:
            default_headers.update(headers)

        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=default_headers,
        )
        self._closed = False

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
        """Make an HTTP request and handle errors.

        Automatically retries on 429 responses when rate-limit retry is enabled.
        """
        return await self._do_request(method, self._url(path), json=json, params=params)

    async def _raw_request(
        self,
        method: str,
        raw_path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with a raw path (no base-path prefix)."""
        return await self._do_request(method, raw_path, json=json, params=params)

    async def _do_request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with optional 429 retry logic."""
        cfg = self._retry_config
        max_attempts = (1 + cfg.max_retries) if cfg.enabled else 1

        for attempt in range(max_attempts):
            try:
                response = await self._client.request(
                    method, url, json=json, params=params,
                    headers={"X-Request-ID": str(uuid.uuid4())},
                )
            except httpx.ConnectError as e:
                raise OJSConnectionError(
                    f"Failed to connect to OJS server at {self._base_url}: {e}"
                ) from e
            except httpx.TimeoutException as e:
                raise OJSTimeoutError(f"Request to OJS server timed out: {e}") from e
            except (httpx.ReadError, httpx.WriteError, httpx.PoolTimeout) as e:
                raise OJSConnectionError(
                    f"Communication error with OJS server at {self._base_url}: {e}"
                ) from e

            if response.status_code == 429 and cfg.enabled and attempt < cfg.max_retries:
                retry_after: float | None = None
                raw = response.headers.get("retry-after")
                if raw is not None:
                    with contextlib.suppress(ValueError):
                        retry_after = float(raw)
                await sleep_before_retry(attempt, retry_after, cfg)
                continue

            if response.status_code in (502, 503, 504) and cfg.retry_server_errors and cfg.enabled and attempt < cfg.max_retries:
                await sleep_before_retry(attempt, None, cfg)
                continue

            if response.status_code >= 400:
                try:
                    body = response.json()
                except ValueError:
                    body = {"error": {"message": response.text or "Unknown error", "code": "parse_error"}}
                headers = dict(response.headers)
                raise_for_error(response.status_code, body, headers)

            if response.status_code == 204:
                return {}
            try:
                result: dict[str, Any] = response.json()
            except ValueError as e:
                raise OJSConnectionError(
                    f"Invalid JSON response from OJS server: {e}"
                ) from e
            return result

        # All retry attempts exhausted on 429 — raise the last response as error.
        # This path is reached when the for loop completes without returning.
        raise OJSConnectionError(
            f"Request to OJS server failed after {max_attempts} attempts"
        )

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
        return await self._request("POST", "/workers/nack", json={"job_id": job_id, "error": error})

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

    # --- Progress ---

    async def progress(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/workers/progress", json=body)

    async def get_progress(self, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/jobs/{job_id}/progress")

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
        data = await self._request("POST", "/workflows", json=definition.to_dict())
        return Workflow.from_dict(data["workflow"])

    async def get_workflow(self, workflow_id: str) -> Workflow:
        data = await self._request("GET", f"/workflows/{workflow_id}")
        return Workflow.from_dict(data["workflow"])

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/workflows/{workflow_id}")

    # --- Manifest ---

    async def manifest(self) -> dict[str, Any]:
        return await self._raw_request("GET", "/ojs/manifest")

    # --- Dead Letter Operations ---

    async def list_dead_letter_jobs(
        self,
        queue: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if queue is not None:
            params["queue"] = queue
        return await self._request("GET", "/dead-letter", params=params)

    async def retry_dead_letter_job(self, job_id: str) -> Job:
        data = await self._request("POST", f"/dead-letter/{job_id}/retry")
        return Job.from_dict(data["job"])

    async def delete_dead_letter_job(self, job_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/dead-letter/{job_id}")

    # --- Cron Operations ---

    async def list_cron_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._request("GET", "/cron", params=params)

    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/cron", json=body)

    async def unregister_cron_job(self, name: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/cron/{name}")

    # --- Schema Operations ---

    async def list_schemas(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._request("GET", "/schemas", params=params)

    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/schemas", json=body)

    async def get_schema(self, uri: str) -> dict[str, Any]:
        encoded_uri = quote(uri, safe="")
        return await self._request("GET", f"/schemas/{encoded_uri}")

    async def delete_schema(self, uri: str) -> dict[str, Any]:
        encoded_uri = quote(uri, safe="")
        return await self._request("DELETE", f"/schemas/{encoded_uri}")

    # --- Lifecycle ---

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def close(self) -> None:
        if self._owns_client and not self._closed:
            self._closed = True
            try:
                await asyncio.wait_for(self._client.aclose(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("HTTP client close timed out after 5s")

    # --- Generic Request (used by durable execution) ---

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(method, path, json=body)
