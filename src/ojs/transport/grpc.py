"""gRPC transport for OJS.

Implements the OJS gRPC Protocol Binding (Layer 3) using grpcio.
This is an optional transport — install with: pip install openjobspec[grpc]

Usage::

    from ojs.transport.grpc import GrpcTransport

    transport = GrpcTransport("localhost:9090")
    client = ojs.Client(transport=transport)
"""

from __future__ import annotations

from typing import Any

from ojs.errors import (
    OJSConnectionError,
    OJSTimeoutError,
    OJSAPIError,
    OJSErrorDetail,
    DuplicateJobError,
    JobNotFoundError,
    QueuePausedError,
    RateLimitedError,
)
from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.transport.base import Transport
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
        channel: Any = None,
    ) -> None:
        try:
            import grpc.aio  # noqa: F401
        except ImportError as exc:
            msg = (
                "grpcio is required for gRPC transport. "
                "Install with: pip install openjobspec[grpc]"
            )
            raise ImportError(msg) from exc

        import grpc.aio as grpc_aio

        self._target = target
        self._timeout = timeout
        self._owns_channel = channel is None
        self._channel = channel or grpc_aio.insecure_channel(target)

        # Build default metadata
        meta: list[tuple[str, str]] = []
        if api_key:
            meta.append(("x-ojs-api-key", api_key))
        if auth:
            meta.append(("authorization", auth))
        if metadata:
            meta.extend(metadata.items())
        self._metadata = tuple(meta) if meta else None

        # Build the stub dynamically to avoid requiring generated code
        self._stub = self._create_stub()

    def _create_stub(self) -> Any:
        """Create gRPC method stubs using the channel directly."""
        import grpc

        service = "ojs.v1.OJSService"

        def _unary(method: str, req_ser: Any, resp_deser: Any) -> Any:
            return self._channel.unary_unary(
                f"/{service}/{method}",
                request_serializer=req_ser,
                response_deserializer=resp_deser,
            )

        # We use raw bytes serialization with a simple JSON-based approach
        # For proper proto serialization, we need the generated pb2 modules
        # Instead, we'll try to import generated code, falling back to a
        # dynamic approach
        return _GrpcStub(self._channel, service)

    # --- Job Operations ---

    async def push(self, body: dict[str, Any]) -> Job:
        request = {
            "type": body["type"],
            "args": [_to_proto_value(a) for a in body.get("args", [])],
        }
        opts = _build_enqueue_options(body)
        if opts:
            request["options"] = opts

        response = await self._call("Enqueue", request)
        return Job.from_dict(_from_proto_job(response.get("job", {})))

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        entries = []
        for j in jobs:
            entry: dict[str, Any] = {
                "type": j["type"],
                "args": [_to_proto_value(a) for a in j.get("args", [])],
            }
            opts = _build_enqueue_options(j)
            if opts:
                entry["options"] = opts
            entries.append(entry)

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
        request: dict[str, Any] = {
            "queues": queues,
            "count": count,
        }
        if worker_id:
            request["worker_id"] = worker_id

        response = await self._call("Fetch", request)
        return [Job.from_dict(_from_proto_job(j)) for j in response.get("jobs", [])]

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        request: dict[str, Any] = {"job_id": job_id}
        if result is not None:
            request["result"] = result
        response = await self._call("Ack", request)
        return {"acknowledged": response.get("acknowledged", True)}

    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        request: dict[str, Any] = {
            "job_id": job_id,
            "error": {
                "code": error.get("code", ""),
                "message": error.get("message", ""),
                "retryable": error.get("retryable", False),
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
        request: dict[str, Any] = {"worker_id": worker_id}
        if active_jobs:
            request["id"] = active_jobs[0]
        response = await self._call("Heartbeat", request)
        directed = response.get("directed_state", "WORKER_STATE_RUNNING")
        state_map: dict[str, str] = {
            "WORKER_STATE_RUNNING": "running",
            "WORKER_STATE_QUIET": "quiet",
            "WORKER_STATE_TERMINATE": "terminate",
        }
        return {"state": state_map.get(directed, "running")}

    # --- Progress ---

    async def progress(self, body: dict[str, Any]) -> dict[str, Any]:
        # Progress is not a standard gRPC RPC in the proto
        return {}

    # --- Queue Operations ---

    async def list_queues(self) -> list[Queue]:
        response = await self._call("ListQueues", {})
        queues = []
        for q in response.get("queues", []):
            queues.append(
                Queue.from_dict({
                    "name": q.get("name", ""),
                    "status": "paused" if q.get("paused") else "active",
                })
            )
        return queues

    async def queue_stats(self, queue_name: str) -> QueueStats:
        response = await self._call("QueueStats", {"queue": queue_name})
        stats = response.get("stats", {})
        return QueueStats.from_dict({
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
        })

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        await self._call("PauseQueue", {"queue": queue_name})
        return {"status": "paused"}

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        await self._call("ResumeQueue", {"queue": queue_name})
        return {"status": "active"}

    # --- Workflow Operations ---

    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow:
        steps = []
        for s in definition.steps:
            step: dict[str, Any] = {
                "id": s.id,
                "type": s.type,
                "args": [_to_proto_value(a) for a in (s.args or [])],
            }
            if s.depends_on:
                step["depends_on"] = s.depends_on
            steps.append(step)

        response = await self._call(
            "CreateWorkflow",
            {"name": definition.name, "steps": steps},
        )
        return Workflow.from_dict(_from_proto_workflow(response.get("workflow", {})))

    async def get_workflow(self, workflow_id: str) -> Workflow:
        response = await self._call("GetWorkflow", {"workflow_id": workflow_id})
        return Workflow.from_dict(_from_proto_workflow(response.get("workflow", {})))

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        await self._call("CancelWorkflow", {"workflow_id": workflow_id})
        return {"state": "cancelled"}

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
        request: dict[str, Any] = {"limit": limit}
        if queue is not None:
            request["queue"] = queue
        response = await self._call("ListDeadLetter", request)
        return {
            "jobs": [_from_proto_job(j) for j in response.get("jobs", [])],
            "pagination": {"total": response.get("total_count", 0)},
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
        return {
            "cron_jobs": [
                {
                    "name": e.get("name", ""),
                    "cron": e.get("cron", ""),
                    "timezone": e.get("timezone", "UTC"),
                    "type": e.get("type", ""),
                }
                for e in response.get("entries", [])
            ],
        }

    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]:
        request: dict[str, Any] = {
            "name": body["name"],
            "cron": body["cron"],
            "type": body["type"],
            "args": [_to_proto_value(a) for a in body.get("args", [])],
        }
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
        # Schema operations are not defined in the gRPC proto
        return {"schemas": [], "pagination": {"total": 0}}

    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]:
        return body

    async def get_schema(self, uri: str) -> dict[str, Any]:
        return {}

    async def delete_schema(self, uri: str) -> dict[str, Any]:
        return {}

    # --- Lifecycle ---

    async def health(self) -> dict[str, Any]:
        response = await self._call("Health", {})
        status_map: dict[str, str] = {
            "HEALTH_STATUS_OK": "ok",
            "HEALTH_STATUS_DEGRADED": "degraded",
            "HEALTH_STATUS_UNHEALTHY": "unhealthy",
        }
        return {"status": status_map.get(response.get("status", ""), "ok")}

    async def close(self) -> None:
        if self._owns_channel:
            await self._channel.close()

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
            return response  # type: ignore[no-any-return]
        except grpc.aio.AioRpcError as e:
            raise _map_grpc_error(e) from e
        except Exception as e:
            raise OJSConnectionError(
                f"gRPC call {method} failed: {e}"
            ) from e


class _GrpcStub:
    """Dynamic gRPC stub that uses JSON serialization via proto reflection.

    When generated proto modules are not available, this stub uses grpc
    channel methods directly with a simple dict-based request/response format.
    """

    def __init__(self, channel: Any, service: str) -> None:
        self._channel = channel
        self._service = service
        self._methods: dict[str, Any] = {}

    async def call(
        self,
        method: str,
        request: dict[str, Any],
        *,
        timeout: float = 30.0,
        metadata: tuple[tuple[str, str], ...] | None = None,
    ) -> dict[str, Any]:
        """Make a unary-unary gRPC call.

        This uses the protobuf JSON format for serialization,
        leveraging google.protobuf.json_format when available.
        """
        import grpc

        try:
            from google.protobuf import descriptor_pool, json_format, symbol_database
            from google.protobuf import descriptor_pb2  # noqa: F401

            return await self._call_with_proto(
                method, request, timeout=timeout, metadata=metadata
            )
        except ImportError:
            # Without protobuf, we can't make actual gRPC calls
            raise OJSConnectionError(
                "grpcio-tools or protobuf package required for gRPC transport. "
                "Install with: pip install openjobspec[grpc]"
            )

    async def _call_with_proto(
        self,
        method: str,
        request: dict[str, Any],
        *,
        timeout: float,
        metadata: tuple[tuple[str, str], ...] | None,
    ) -> dict[str, Any]:
        """Make call using protobuf serialization."""
        import grpc

        # Use raw bytes channel method
        serialized_request = _dict_to_proto_bytes(method, request)
        full_method = f"/{self._service}/{method}"

        call = self._channel.unary_unary(
            full_method,
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        response_bytes = await call(
            serialized_request,
            timeout=timeout,
            metadata=metadata,
        )

        return _proto_bytes_to_dict(method, response_bytes)


def _dict_to_proto_bytes(method: str, data: dict[str, Any]) -> bytes:
    """Serialize a dict to protobuf bytes for the given RPC method."""
    try:
        from google.protobuf import json_format, descriptor_pool, symbol_database

        db = symbol_database.Default()
        pool = descriptor_pool.Default()

        request_type = f"ojs.v1.{method}Request"
        descriptor = pool.FindMessageTypeByName(request_type)
        message_class = db.GetPrototype(descriptor)
        message = json_format.ParseDict(data, message_class())
        return message.SerializeToString()  # type: ignore[no-any-return]
    except Exception:
        # Fallback: try simple JSON encoding
        import json

        return json.dumps(data).encode("utf-8")


def _proto_bytes_to_dict(method: str, data: bytes) -> dict[str, Any]:
    """Deserialize protobuf bytes to a dict for the given RPC method."""
    try:
        from google.protobuf import json_format, descriptor_pool, symbol_database

        db = symbol_database.Default()
        pool = descriptor_pool.Default()

        response_type = f"ojs.v1.{method}Response"
        descriptor = pool.FindMessageTypeByName(response_type)
        message_class = db.GetPrototype(descriptor)
        message = message_class()
        message.ParseFromString(data)
        result: dict[str, Any] = json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
        )
        return result
    except Exception:
        import json

        return json.loads(data.decode("utf-8"))  # type: ignore[no-any-return]


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
        return {
            "struct_value": {
                "fields": {k: _to_proto_value(v) for k, v in value.items()}
            }
        }
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
        return {
            k: _from_proto_value(v)
            for k, v in value["struct_value"].get("fields", {}).items()
        }
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
    if job is None:
        return {}
    if not isinstance(job, dict):
        # If it's a protobuf message object, convert to dict
        try:
            from google.protobuf import json_format

            job = json_format.MessageToDict(job, preserving_proto_field_name=True)
        except (ImportError, AttributeError):
            return {}

    return {
        "id": job.get("id", ""),
        "type": job.get("type", ""),
        "queue": job.get("queue", "default"),
        "args": [_from_proto_value(a) for a in job.get("args", [])],
        "state": _map_job_state(job.get("state", "available")),
        "priority": job.get("priority", 0),
        "attempt": job.get("attempt", 0),
        "max_attempts": job.get("max_attempts", 0),
        "created_at": job.get("created_at"),
        "enqueued_at": job.get("enqueued_at"),
        "scheduled_at": job.get("scheduled_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "tags": job.get("tags", []),
    }


def _from_proto_workflow(workflow: dict[str, Any] | Any) -> dict[str, Any]:
    """Convert a proto Workflow to the dict format expected by Workflow.from_dict()."""
    if workflow is None:
        return {}
    if not isinstance(workflow, dict):
        try:
            from google.protobuf import json_format

            workflow = json_format.MessageToDict(
                workflow, preserving_proto_field_name=True
            )
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
    opts: dict[str, Any] = {}
    if "queue" in body and body["queue"]:
        opts["queue"] = body["queue"]
    if "priority" in body:
        opts["priority"] = body["priority"]
    if "tags" in body:
        opts["tags"] = body["tags"]
    if "options" in body and body["options"]:
        opts.update(body["options"])
    return opts if opts else None


def _map_grpc_error(error: Any) -> Exception:
    """Map a gRPC error to the appropriate OJS error type."""
    import grpc

    code = error.code()
    message = error.details() or str(error)
    detail = OJSErrorDetail(
        code=_grpc_code_to_ojs_code(code),
        message=message,
        retryable=code
        in (
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.INTERNAL,
        ),
    )

    status_code = _grpc_code_to_http_status(code)

    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return OJSAPIError(status_code, detail)
    if code == grpc.StatusCode.NOT_FOUND:
        return JobNotFoundError(status_code, detail)
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return DuplicateJobError(status_code, detail)
    if code == grpc.StatusCode.FAILED_PRECONDITION:
        return QueuePausedError(status_code, detail)
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return RateLimitedError(status_code, detail)
    if code == grpc.StatusCode.UNAVAILABLE:
        return OJSConnectionError(f"gRPC server unavailable: {message}")
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return OJSTimeoutError(f"gRPC deadline exceeded: {message}")

    return OJSAPIError(status_code, detail)


def _grpc_code_to_ojs_code(code: Any) -> str:
    """Map gRPC status code to OJS error code string."""
    import grpc

    mapping: dict[Any, str] = {
        grpc.StatusCode.INVALID_ARGUMENT: "invalid_request",
        grpc.StatusCode.NOT_FOUND: "not_found",
        grpc.StatusCode.ALREADY_EXISTS: "duplicate",
        grpc.StatusCode.FAILED_PRECONDITION: "queue_paused",
        grpc.StatusCode.RESOURCE_EXHAUSTED: "rate_limited",
        grpc.StatusCode.UNAVAILABLE: "connection_error",
        grpc.StatusCode.DEADLINE_EXCEEDED: "timeout",
        grpc.StatusCode.PERMISSION_DENIED: "permission_denied",
        grpc.StatusCode.UNIMPLEMENTED: "unimplemented",
        grpc.StatusCode.INTERNAL: "internal",
    }
    return mapping.get(code, "unknown")


def _grpc_code_to_http_status(code: Any) -> int:
    """Map gRPC status code to approximate HTTP status code."""
    import grpc

    mapping: dict[Any, int] = {
        grpc.StatusCode.OK: 200,
        grpc.StatusCode.INVALID_ARGUMENT: 400,
        grpc.StatusCode.NOT_FOUND: 404,
        grpc.StatusCode.ALREADY_EXISTS: 409,
        grpc.StatusCode.FAILED_PRECONDITION: 422,
        grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
        grpc.StatusCode.PERMISSION_DENIED: 403,
        grpc.StatusCode.UNAUTHENTICATED: 401,
        grpc.StatusCode.UNAVAILABLE: 503,
        grpc.StatusCode.DEADLINE_EXCEEDED: 504,
        grpc.StatusCode.UNIMPLEMENTED: 501,
        grpc.StatusCode.INTERNAL: 500,
    }
    return mapping.get(code, 500)
