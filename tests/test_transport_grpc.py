"""Tests for the gRPC transport layer."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ojs
from ojs.workflow import WorkflowDefinition, WorkflowStep


# --- Helper: mock gRPC modules ---


class FakeGrpcStatusCode:
    """Fake grpc.StatusCode enum."""

    OK = "OK"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    FAILED_PRECONDITION = "FAILED_PRECONDITION"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    UNAVAILABLE = "UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UNIMPLEMENTED = "UNIMPLEMENTED"
    INTERNAL = "INTERNAL"


class FakeAioRpcError(Exception):
    """Fake grpc.aio.AioRpcError for testing."""

    def __init__(self, code: str, details: str = "") -> None:
        self._code = code
        self._details = details
        super().__init__(details)

    def code(self) -> str:
        return self._code

    def details(self) -> str:
        return self._details


class FakeChannel:
    """Fake async gRPC channel."""

    def __init__(self) -> None:
        self._closed = False

    def unary_unary(self, method: str, **kwargs: Any) -> Any:
        return AsyncMock()

    async def close(self) -> None:
        self._closed = True


@pytest.fixture
def mock_grpc(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch grpc modules for import."""
    fake_grpc = MagicMock()
    fake_grpc.StatusCode = FakeGrpcStatusCode
    fake_grpc.aio.AioRpcError = FakeAioRpcError
    fake_grpc.aio.insecure_channel = MagicMock(return_value=FakeChannel())

    import sys

    monkeypatch.setitem(sys.modules, "grpc", fake_grpc)
    monkeypatch.setitem(sys.modules, "grpc.aio", fake_grpc.aio)

    return {"grpc": fake_grpc}


def _create_transport(
    mock_grpc: dict[str, Any],
    target: str = "localhost:9090",
    **kwargs: Any,
) -> Any:
    """Create a GrpcTransport with mocked gRPC dependencies."""
    from ojs.transport.grpc import GrpcTransport

    channel = FakeChannel()
    mock_grpc["grpc"].aio.insecure_channel.return_value = channel
    return GrpcTransport(target, channel=channel, **kwargs)


# --- Tests ---


class TestGrpcTransportInit:
    def test_creates_with_minimal_config(self, mock_grpc: dict[str, Any]) -> None:
        transport = _create_transport(mock_grpc)
        assert transport is not None

    def test_creates_with_all_options(self, mock_grpc: dict[str, Any]) -> None:
        transport = _create_transport(
            mock_grpc,
            api_key="test-key",
            auth="Bearer token123",
            timeout=5.0,
            metadata={"x-custom": "value"},
        )
        assert transport is not None
        assert transport._timeout == 5.0

    def test_metadata_includes_api_key(self, mock_grpc: dict[str, Any]) -> None:
        transport = _create_transport(mock_grpc, api_key="my-key")
        assert transport._metadata is not None
        meta_dict = dict(transport._metadata)
        assert meta_dict["x-ojs-api-key"] == "my-key"

    def test_metadata_includes_auth(self, mock_grpc: dict[str, Any]) -> None:
        transport = _create_transport(mock_grpc, auth="Bearer tok")
        assert transport._metadata is not None
        meta_dict = dict(transport._metadata)
        assert meta_dict["authorization"] == "Bearer tok"

    def test_metadata_includes_custom_entries(self, mock_grpc: dict[str, Any]) -> None:
        transport = _create_transport(
            mock_grpc,
            metadata={"x-tenant-id": "t1", "x-request-id": "r1"},
        )
        assert transport._metadata is not None
        meta_dict = dict(transport._metadata)
        assert meta_dict["x-tenant-id"] == "t1"
        assert meta_dict["x-request-id"] == "r1"

    def test_uses_provided_channel(self, mock_grpc: dict[str, Any]) -> None:
        channel = FakeChannel()
        from ojs.transport.grpc import GrpcTransport

        transport = GrpcTransport("localhost:9090", channel=channel)
        assert transport._owns_channel is False

    def test_owns_channel_when_not_injected(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import GrpcTransport

        transport = GrpcTransport("localhost:9090")
        assert transport._owns_channel is True


class TestGrpcTransportClose:
    async def test_close_owned_channel(self, mock_grpc: dict[str, Any]) -> None:
        channel = FakeChannel()
        mock_grpc["grpc"].aio.insecure_channel.return_value = channel
        from ojs.transport.grpc import GrpcTransport

        transport = GrpcTransport("localhost:9090")
        await transport.close()
        assert channel._closed

    async def test_close_injected_channel(self, mock_grpc: dict[str, Any]) -> None:
        channel = FakeChannel()
        from ojs.transport.grpc import GrpcTransport

        transport = GrpcTransport("localhost:9090", channel=channel)
        await transport.close()
        # Injected channel should NOT be closed
        assert not channel._closed


class TestProtoValueConversion:
    """Test the _to_proto_value and _from_proto_value helpers."""

    def test_string_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value("hello")
        assert proto == {"string_value": "hello"}
        assert _from_proto_value(proto) == "hello"

    def test_number_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value(42)
        assert proto == {"number_value": 42}
        assert _from_proto_value(proto) == 42

    def test_bool_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value(True)
        assert proto == {"bool_value": True}
        assert _from_proto_value(proto) is True

    def test_null_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value(None)
        assert proto == {"null_value": 0}
        assert _from_proto_value(proto) is None

    def test_list_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value(["a", 1])
        assert proto == {
            "list_value": {
                "values": [{"string_value": "a"}, {"number_value": 1}]
            }
        }
        assert _from_proto_value(proto) == ["a", 1]

    def test_dict_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _to_proto_value, _from_proto_value

        proto = _to_proto_value({"key": "val"})
        assert proto == {
            "struct_value": {"fields": {"key": {"string_value": "val"}}}
        }
        assert _from_proto_value(proto) == {"key": "val"}


class TestJobStateMapping:
    def test_maps_proto_state_strings(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_job_state

        assert _map_job_state("JOB_STATE_AVAILABLE") == "available"
        assert _map_job_state("JOB_STATE_ACTIVE") == "active"
        assert _map_job_state("JOB_STATE_COMPLETED") == "completed"
        assert _map_job_state("JOB_STATE_CANCELLED") == "cancelled"
        assert _map_job_state("JOB_STATE_DISCARDED") == "discarded"
        assert _map_job_state("JOB_STATE_RETRYABLE") == "retryable"
        assert _map_job_state("JOB_STATE_SCHEDULED") == "scheduled"
        assert _map_job_state("JOB_STATE_PENDING") == "pending"

    def test_maps_numeric_states(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_job_state

        assert _map_job_state(2) == "available"
        assert _map_job_state(4) == "active"
        assert _map_job_state(5) == "completed"
        assert _map_job_state(7) == "cancelled"


class TestFromProtoJob:
    def test_converts_proto_job_dict(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_job

        proto_job = {
            "id": "job-123",
            "type": "email.send",
            "queue": "default",
            "state": "JOB_STATE_AVAILABLE",
            "args": [{"string_value": "user@example.com"}],
            "priority": 0,
            "attempt": 0,
            "max_attempts": 3,
            "tags": ["urgent"],
        }
        result = _from_proto_job(proto_job)
        assert result["id"] == "job-123"
        assert result["type"] == "email.send"
        assert result["state"] == "available"
        assert result["args"] == ["user@example.com"]
        assert result["tags"] == ["urgent"]

    def test_handles_empty_job(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_job

        result = _from_proto_job({})
        assert result["id"] == ""
        assert result["state"] == "available"
        assert result["args"] == []

    def test_handles_none(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_job

        result = _from_proto_job(None)
        assert result == {}


class TestFromProtoWorkflow:
    def test_converts_proto_workflow(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_workflow

        proto_wf = {
            "id": "wf-001",
            "name": "my-chain",
            "state": "WORKFLOW_STATE_RUNNING",
            "steps": [
                {
                    "id": "step-1",
                    "type": "email.send",
                    "state": "WORKFLOW_STEP_STATE_ACTIVE",
                    "job_id": "j-1",
                },
                {
                    "id": "step-2",
                    "type": "notify",
                    "state": "WORKFLOW_STEP_STATE_WAITING",
                    "depends_on": ["step-1"],
                },
            ],
        }
        result = _from_proto_workflow(proto_wf)
        assert result["id"] == "wf-001"
        assert result["state"] == "running"
        assert len(result["steps"]) == 2
        assert result["steps"][0]["state"] == "active"
        assert result["steps"][1]["state"] == "waiting"
        assert result["steps"][1]["depends_on"] == ["step-1"]


class TestErrorMapping:
    def test_maps_invalid_argument(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.INVALID_ARGUMENT, "bad request")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.OJSAPIError)
        assert result.status_code == 400

    def test_maps_not_found(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.NOT_FOUND, "job not found")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.JobNotFoundError)
        assert result.status_code == 404

    def test_maps_already_exists(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.ALREADY_EXISTS, "duplicate")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.DuplicateJobError)

    def test_maps_failed_precondition(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.FAILED_PRECONDITION, "queue paused")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.QueuePausedError)

    def test_maps_resource_exhausted(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.RESOURCE_EXHAUSTED, "rate limited")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.RateLimitedError)

    def test_maps_unavailable(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.UNAVAILABLE, "service unavailable")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.OJSConnectionError)

    def test_maps_deadline_exceeded(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.DEADLINE_EXCEEDED, "timed out")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.OJSTimeoutError)

    def test_maps_internal(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(FakeGrpcStatusCode.INTERNAL, "server error")
        result = _map_grpc_error(err)
        assert isinstance(result, ojs.OJSAPIError)
        assert result.status_code == 500


class TestBuildEnqueueOptions:
    def test_empty_when_no_options(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _build_enqueue_options

        assert _build_enqueue_options({"type": "test", "args": []}) is None

    def test_includes_queue(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _build_enqueue_options

        result = _build_enqueue_options({"type": "test", "queue": "email"})
        assert result is not None
        assert result["queue"] == "email"

    def test_includes_priority(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _build_enqueue_options

        result = _build_enqueue_options({"type": "test", "priority": 10})
        assert result is not None
        assert result["priority"] == 10

    def test_includes_tags(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _build_enqueue_options

        result = _build_enqueue_options({"type": "test", "tags": ["urgent"]})
        assert result is not None
        assert result["tags"] == ["urgent"]
