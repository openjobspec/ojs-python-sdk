"""gRPC transport for OJS.

Implements the OJS gRPC Protocol Binding (Layer 3) using grpcio.
This is an optional transport — install with: pip install openjobspec[grpc]

Usage::

    from ojs.transport.grpc import GrpcTransport

    transport = GrpcTransport("localhost:9090")
    client = ojs.Client(transport=transport)
"""

from __future__ import annotations

from typing import Any, cast

from ojs.errors import (
    OJSCapabilityError,
    OJSConnectionError,
    OJSError,
)
from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.transport.base import Transport
from ojs.transport.grpc.channel import GrpcChannel, GrpcUnaryStub
from ojs.transport.grpc.descriptor_registry import DescriptorRegistry
from ojs.transport.grpc.enqueue_projection import project_enqueue
from ojs.transport.grpc.job_projection import project_job
from ojs.transport.grpc.paging import collect_offset_page, slice_offset_page
from ojs.transport.grpc.protobuf_codec import ProtobufCodec
from ojs.transport.grpc.rpc_error_mapper import (
    grpc_code_to_http_status,
    grpc_code_to_ojs_code,
    map_grpc_error,
)
from ojs.transport.grpc.worker_lease import (
    aggregate_heartbeat_states,
    fetch_request,
    heartbeat_requests,
)
from ojs.transport.grpc.workflow_projection import project_workflow
from ojs.workflow import Workflow, WorkflowDefinition

# Job state mapping from proto enum strings to SDK state strings
_JOB_STATE_MAP: dict[str, str] = {
    "JOB_STATE_SCHEDULED": "scheduled",
    "JOB_STATE_AVAILABLE": "available",
    "JOB_STATE_PENDING": "pending",
    "JOB_STATE_ACTIVE": "active",
    "JOB_STATE_COMPLETED": "completed",
    "JOB_STATE_RETRYABLE": "retryable",
    "JOB_STATE_CANCELLED": "cancelled",
    "JOB_STATE_DISCARDED": "discarded",
}

_WORKFLOW_STATE_MAP: dict[str, str] = {
    "WORKFLOW_STATE_RUNNING": "running",
    "WORKFLOW_STATE_COMPLETED": "completed",
    "WORKFLOW_STATE_FAILED": "failed",
    "WORKFLOW_STATE_CANCELLED": "cancelled",
}

_STEP_STATE_MAP: dict[str, str] = {
    "WORKFLOW_STEP_STATE_WAITING": "waiting",
    "WORKFLOW_STEP_STATE_PENDING": "pending",
    "WORKFLOW_STEP_STATE_ACTIVE": "active",
    "WORKFLOW_STEP_STATE_COMPLETED": "completed",
    "WORKFLOW_STEP_STATE_FAILED": "failed",
    "WORKFLOW_STEP_STATE_CANCELLED": "cancelled",
}


class GrpcTransport(Transport):
    """gRPC transport using grpcio with asyncio support.

    Implements the OJS gRPC binding specification. Requires the ``grpcio``
    package (install with ``pip install openjobspec[grpc]``).

    Args:
        target: The gRPC server address (e.g., "localhost:9090").
        timeout: Default deadline in seconds for unary RPCs. Default: 30.
        api_key: Optional API key for authentication (sent as ``x-ojs-api-key`` metadata).
        auth: Optional Bearer token (sent as ``authorization`` metadata).
        metadata: Additional metadata key-value pairs to include in every RPC.
        channel: Optional pre-configured ``grpc.aio.Channel`` to use.
    """

    def __init__(
        self,
        target: str,
        *,
        timeout: float = 30.0,
        api_key: str | None = None,
        auth: str | None = None,
        metadata: dict[str, str] | None = None,
        channel: GrpcChannel | None = None,
    ) -> None:
        try:
            import grpc.aio  # noqa: F401
        except ImportError as exc:
            msg = (
                "grpcio is required for gRPC transport. Install with: pip install openjobspec[grpc]"
            )
            raise ImportError(msg) from exc

        import grpc.aio as grpc_aio

        self._target = target
        self._timeout = timeout
        self._owns_channel = channel is None
        self._channel = channel or cast(
            GrpcChannel,
            grpc_aio.insecure_channel(target),
        )

        # Build default metadata
        meta: list[tuple[str, str]] = []
        if api_key:
            meta.append(("x-ojs-api-key", api_key))
        if auth:
            meta.append(("authorization", auth))
        if metadata:
            meta.extend(metadata.items())
        self._metadata = tuple(meta) if meta else None

        self._stub = self._create_stub()

    def _create_stub(self) -> GrpcUnaryStub:
        """Create a validated descriptor-backed RPC stub."""
        return GrpcUnaryStub(self._channel, DescriptorRegistry())

    # --- Job Operations ---

    async def push(self, body: dict[str, Any]) -> Job:
        response = await self._call("Enqueue", project_enqueue(body))
        return Job.from_dict(_from_proto_job(response.get("job", {})))

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        entries = [project_enqueue(job) for job in jobs]
        response = await self._call("EnqueueBatch", {"jobs": entries})
        return [Job.from_dict(_from_proto_job(j)) for j in response.get("jobs", [])]

    async def info(self, job_id: str) -> Job:
        response = await self._call("GetJob", {"job_id": job_id})
        return Job.from_dict(_from_proto_job(response.get("job", {})))

    async def cancel(self, job_id: str) -> Job:
        response = await self._call("CancelJob", {"job_id": job_id})
        return Job.from_dict(_from_proto_job(response.get("job", {})))

    # --- Worker Operations ---

    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]:
        request = fetch_request(
            queues,
            count,
            worker_id,
            visibility_timeout_ms,
        )
        response = await self._call("Fetch", request)
        return [Job.from_dict(_from_proto_job(j)) for j in response.get("jobs", [])]

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        request: dict[str, Any] = {"job_id": job_id}
        if result is not None:
            request["result"] = result
        response = await self._call("Ack", request)
        return {"acknowledged": response.get("acknowledged", False)}

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        error_code = error.get("code", error.get("type", ""))
        request: dict[str, Any] = {
            "job_id": job_id,
            "error": {
                "code": error_code,
                "message": error.get("message", ""),
                "retryable": error.get("retryable", False),
                "attempt": error.get("attempt", 0),
                "occurred_at": error.get("occurred_at"),
                "backtrace": error.get("backtrace", error.get("stack", "")),
                "details": error.get("details", {}),
            },
        }
        response = await self._call("Nack", request)
        state_str = _map_job_state(response.get("state", ""))
        return {
            "state": state_str,
            "next_attempt_at": response.get("next_attempt_at"),
        }

    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        active_job_ids = list(active_jobs or ())
        responses = [
            await self._call("Heartbeat", request)
            for request in heartbeat_requests(
                worker_id,
                active_job_ids,
                visibility_timeout_ms,
            )
        ]
        return {
            "state": aggregate_heartbeat_states(responses),
            "jobs_extended": active_job_ids,
        }

    # --- Progress ---

    async def progress(self, body: dict[str, Any]) -> dict[str, Any]:
        raise OJSCapabilityError(
            "The canonical OJS v1 gRPC service has no progress RPC. "
            "Use HTTP transport for progress reporting."
        )

    # --- Queue Operations ---

    async def list_queues(self) -> list[Queue]:
        queues: list[Queue] = []
        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            request: dict[str, Any] = {"limit": 100}
            if cursor:
                request["cursor"] = cursor
            response = await self._call("ListQueues", request)
            for queue_data in response.get("queues", []):
                queues.append(
                    Queue.from_dict(
                        {
                            "name": queue_data.get("name", ""),
                            "status": "paused" if queue_data.get("paused") else "active",
                        }
                    )
                )
            next_cursor = response.get("next_cursor", "")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise OJSConnectionError("gRPC queue pagination returned a repeated cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return queues

    async def queue_stats(self, queue_name: str) -> QueueStats:
        response = await self._call("QueueStats", {"queue": queue_name})
        stats = response.get("stats", {})
        return QueueStats.from_dict(
            {
                "queue": response.get("queue", queue_name),
                "status": "paused" if stats.get("paused") else "active",
                "stats": {
                    "available": stats.get("available", 0),
                    "active": stats.get("active", 0),
                    "scheduled": stats.get("scheduled", 0),
                    "retryable": stats.get("retryable", 0),
                    "dead": stats.get("dead", 0),
                    "completed_last_hour": stats.get("completed_last_hour", 0),
                    "failed_last_hour": stats.get("failed_last_hour", 0),
                },
            }
        )

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        await self._call("PauseQueue", {"queue": queue_name})
        return {"status": "paused"}

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        await self._call("ResumeQueue", {"queue": queue_name})
        return {"status": "active"}

    # --- Workflow Operations ---

    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow:
        response = await self._call("CreateWorkflow", project_workflow(definition))
        return Workflow.from_dict(_from_proto_workflow(response.get("workflow", {})))

    async def get_workflow(self, workflow_id: str) -> Workflow:
        response = await self._call("GetWorkflow", {"workflow_id": workflow_id})
        return Workflow.from_dict(_from_proto_workflow(response.get("workflow", {})))

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        response = await self._call("CancelWorkflow", {"workflow_id": workflow_id})
        return _from_proto_workflow(response.get("workflow", {}))

    # --- Manifest ---

    async def manifest(self) -> dict[str, Any]:
        response = await self._call("Manifest", {})
        return {
            "ojs_version": response.get("ojs_version", ""),
            "implementation": response.get("implementation", {}),
            "conformance_level": response.get("conformance_level", 0),
            "protocols": response.get("protocols", []),
            "backend": response.get("backend", ""),
            "extensions": response.get("extensions", []),
        }

    # --- Dead Letter Operations ---

    async def list_dead_letter_jobs(
        self,
        queue: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        async def fetch_page(page_limit: int, cursor: str) -> dict[str, Any]:
            request: dict[str, Any] = {"limit": page_limit}
            if queue is not None:
                request["queue"] = queue
            if cursor:
                request["cursor"] = cursor
            return await self._call("ListDeadLetter", request)

        page = await collect_offset_page(
            fetch_page,
            items_key="jobs",
            limit=limit,
            offset=offset,
        )
        return {
            "jobs": [_from_proto_job(job) for job in page.items],
            "pagination": {
                "total": page.total,
                "limit": limit,
                "offset": offset,
                "next_cursor": page.next_cursor,
            },
        }

    async def retry_dead_letter_job(self, job_id: str) -> Job:
        response = await self._call("RetryDeadLetter", {"job_id": job_id})
        return Job.from_dict(_from_proto_job(response.get("job", {})))

    async def delete_dead_letter_job(self, job_id: str) -> dict[str, Any]:
        await self._call("DeleteDeadLetter", {"job_id": job_id})
        return {}

    # --- Cron Operations ---

    async def list_cron_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        response = await self._call("ListCron", {})
        entries = response.get("entries", [])
        page = slice_offset_page(entries, limit=limit, offset=offset)
        return {
            "cron_jobs": [
                {
                    "name": e.get("name", ""),
                    "cron": e.get("cron", ""),
                    "timezone": e.get("timezone", "UTC"),
                    "type": e.get("type", ""),
                }
                for e in page.items
            ],
            "pagination": {
                "total": page.total,
                "limit": limit,
                "offset": offset,
            },
        }

    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]:
        enqueue = project_enqueue(
            {
                "type": body["type"],
                "args": body.get("args", []),
                "meta": body.get("meta"),
                "options": body.get("options", {}),
            }
        )
        request: dict[str, Any] = {
            "name": body["name"],
            "cron": body["cron"],
            "type": body["type"],
            "args": body.get("args", []),
        }
        if "options" in enqueue:
            request["options"] = enqueue["options"]
        if "timezone" in body:
            request["timezone"] = body["timezone"]
        response = await self._call("RegisterCron", request)
        return {"name": response.get("name", body["name"])}

    async def unregister_cron_job(self, name: str) -> dict[str, Any]:
        await self._call("UnregisterCron", {"name": name})
        return {}

    # --- Schema Operations ---

    async def list_schemas(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        raise self._unsupported_schema_operation("list")

    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]:
        raise self._unsupported_schema_operation("register")

    async def get_schema(self, uri: str) -> dict[str, Any]:
        raise self._unsupported_schema_operation("get")

    async def delete_schema(self, uri: str) -> dict[str, Any]:
        raise self._unsupported_schema_operation("delete")

    # --- Lifecycle ---

    async def health(self) -> dict[str, Any]:
        response = await self._call("Health", {})
        status_map: dict[str, str] = {
            "HEALTH_STATUS_OK": "ok",
            "HEALTH_STATUS_DEGRADED": "degraded",
            "HEALTH_STATUS_UNHEALTHY": "unhealthy",
        }
        return {"status": status_map.get(response.get("status", ""), "unknown")}

    async def close(self) -> None:
        if self._owns_channel:
            await self._channel.close()

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise OJSCapabilityError(
            "Generic request() is not supported over gRPC. "
            "Durable execution checkpoints require an HTTP transport."
        )

    # --- Internal ---

    async def _call(self, method: str, request: dict[str, Any]) -> dict[str, Any]:
        """Execute a gRPC unary call with error handling."""
        import grpc

        try:
            response = await self._stub.call(
                method,
                request,
                timeout=self._timeout,
                metadata=self._metadata,
            )
            if not isinstance(response, dict):
                raise OJSConnectionError(f"gRPC call {method} returned a non-object response")
            return response
        except grpc.aio.AioRpcError as e:
            raise _map_grpc_error(e) from e
        except (ImportError, OJSError):
            raise
        except Exception as e:
            raise OJSConnectionError(f"gRPC call {method} failed: {e}") from e

    @staticmethod
    def _unsupported_schema_operation(operation: str) -> OJSCapabilityError:
        return OJSCapabilityError(
            f"The canonical OJS v1 gRPC service cannot {operation} schemas. "
            "Use HTTP transport for schema operations."
        )


def _dict_to_proto_bytes(method: str, data: dict[str, Any]) -> bytes:
    """Serialize a request with the canonical generated protobuf schema."""
    return ProtobufCodec().encode_request(method, data)


def _proto_bytes_to_dict(method: str, data: bytes) -> dict[str, Any]:
    """Deserialize a response with the canonical generated protobuf schema."""
    return ProtobufCodec().decode_response(method, data)


# --- Helper functions ---


def _to_proto_value(value: Any) -> Any:
    """Convert a Python value to google.protobuf.Value dict representation."""
    if value is None:
        return {"null_value": 0}
    if isinstance(value, str):
        return {"string_value": value}
    if isinstance(value, bool):
        return {"bool_value": value}
    if isinstance(value, (int, float)):
        return {"number_value": value}
    if isinstance(value, list):
        return {"list_value": {"values": [_to_proto_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"struct_value": {"fields": {k: _to_proto_value(v) for k, v in value.items()}}}
    return {"string_value": str(value)}


def _from_proto_value(value: Any) -> Any:
    """Convert a proto Value dict back to a Python value."""
    if not value or not isinstance(value, dict):
        return value
    if "string_value" in value:
        return value["string_value"]
    if "number_value" in value:
        return value["number_value"]
    if "bool_value" in value:
        return value["bool_value"]
    if "null_value" in value:
        return None
    if "list_value" in value:
        return [_from_proto_value(v) for v in value["list_value"].get("values", [])]
    if "struct_value" in value:
        return {k: _from_proto_value(v) for k, v in value["struct_value"].get("fields", {}).items()}
    return value


def _map_job_state(state: str | int) -> str:
    """Map a proto JobState enum to a lowercase state string."""
    if isinstance(state, str):
        return _JOB_STATE_MAP.get(state, state.lower().replace("job_state_", ""))
    num_map: dict[int, str] = {
        1: "scheduled",
        2: "available",
        3: "pending",
        4: "active",
        5: "completed",
        6: "retryable",
        7: "cancelled",
        8: "discarded",
    }
    return num_map.get(state, "available")


def _from_proto_job(job: dict[str, Any] | Any) -> dict[str, Any]:
    """Convert a proto Job to the dict format expected by Job.from_dict()."""
    if isinstance(job, dict):
        job = {
            **job,
            "args": [_from_proto_value(value) for value in job.get("args", [])],
        }
    return project_job(job)


def _from_proto_workflow(workflow: dict[str, Any] | Any) -> dict[str, Any]:
    """Convert a proto Workflow to the dict format expected by Workflow.from_dict()."""
    if workflow is None:
        return {}
    if not isinstance(workflow, dict):
        try:
            from google.protobuf import json_format

            workflow = json_format.MessageToDict(workflow, preserving_proto_field_name=True)
        except (ImportError, AttributeError):
            return {}

    return {
        "id": workflow.get("id", ""),
        "name": workflow.get("name", ""),
        "state": _WORKFLOW_STATE_MAP.get(
            workflow.get("state", ""), workflow.get("state", "running")
        ),
        "steps": [
            {
                "id": s.get("id", ""),
                "type": s.get("type", ""),
                "state": _STEP_STATE_MAP.get(s.get("state", ""), "pending"),
                "job_id": s.get("job_id", ""),
                "depends_on": s.get("depends_on", []),
            }
            for s in workflow.get("steps", [])
        ],
    }


def _build_enqueue_options(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract enqueue options from a request body."""
    options = project_enqueue(body).get("options")
    return options if isinstance(options, dict) else None


def _grpc_code_to_ojs_code(code: Any) -> str:
    """Compatibility facade for the actor-specific RPC error mapper."""
    return grpc_code_to_ojs_code(code)


def _grpc_code_to_http_status(code: Any) -> int:
    """Compatibility facade for the actor-specific RPC error mapper."""
    return grpc_code_to_http_status(code)


def _map_grpc_error(error: Any) -> Exception:
    """Compatibility facade for the actor-specific RPC error mapper."""
    return map_grpc_error(error)
