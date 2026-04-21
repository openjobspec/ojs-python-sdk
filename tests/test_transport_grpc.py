"""Tests for the gRPC transport layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.protobuf import any_pb2

import ojs
from ojs._generated.ojs.v1 import job_pb2, queue_pb2
from ojs.transport.grpc.channel import GrpcUnaryStub
from ojs.transport.grpc.descriptor_registry import (
    DescriptorRegistry,
    DescriptorRegistryError,
)
from ojs.transport.grpc.enqueue_projection import project_enqueue
from ojs.transport.grpc.job_projection import project_job
from ojs.transport.grpc.protobuf_codec import ProtobufCodec, ProtobufCodecError

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

    def __init__(
        self,
        code: str,
        details: str = "",
        *,
        trailing_metadata: tuple[tuple[str, bytes], ...] = (),
    ) -> None:
        self._code = code
        self._details = details
        self._trailing_metadata = trailing_metadata
        super().__init__(details)

    def code(self) -> str:
        return self._code

    def details(self) -> str:
        return self._details

    def trailing_metadata(self) -> tuple[tuple[str, bytes], ...]:
        return self._trailing_metadata


class FakeChannel:
    """Fake async gRPC channel."""

    def __init__(self) -> None:
        self._closed = False

    def unary_unary(self, method: str, **kwargs: Any) -> Any:
        return AsyncMock()

    async def close(self) -> None:
        self._closed = True


class ProtobufRoundTripChannel:
    """In-memory channel fixture that exercises actual protobuf bytes."""

    def __init__(self) -> None:
        self.request_bytes = b""

    def unary_unary(self, method: str, **kwargs: Any) -> Any:
        assert method == "/ojs.v1.OJSService/Enqueue"

        async def invoke(
            request: bytes,
            *,
            timeout: float,  # noqa: ASYNC109
            metadata: tuple[tuple[str, str], ...] | None,
        ) -> bytes:
            self.request_bytes = request
            decoded = job_pb2.EnqueueRequest.FromString(request)
            assert decoded.type == "email.send"
            assert timeout == 2.0
            assert metadata == (("x-test", "value"),)
            return job_pb2.EnqueueResponse(
                job=job_pb2.Job(
                    id="job-1",
                    type=decoded.type,
                    args=decoded.args,
                    state=job_pb2.JOB_STATE_AVAILABLE,
                )
            ).SerializeToString()

        return invoke


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

    def test_missing_rpc_descriptor_fails_before_rpc(self) -> None:
        registry = DescriptorRegistry()
        with pytest.raises(DescriptorRegistryError, match="Missing"):
            registry.method("Missing")

    def test_missing_service_descriptors_fail_during_construction(self) -> None:
        service = MagicMock()
        service.methods = []
        with pytest.raises(DescriptorRegistryError, match="no RPC descriptors"):
            DescriptorRegistry(service=service)


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
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value("hello")
        assert proto == {"string_value": "hello"}
        assert _from_proto_value(proto) == "hello"

    def test_number_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value(42)
        assert proto == {"number_value": 42}
        assert _from_proto_value(proto) == 42

    def test_bool_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value(True)
        assert proto == {"bool_value": True}
        assert _from_proto_value(proto) is True

    def test_null_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value(None)
        assert proto == {"null_value": 0}
        assert _from_proto_value(proto) is None

    def test_list_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value(["a", 1])
        assert proto == {"list_value": {"values": [{"string_value": "a"}, {"number_value": 1}]}}
        assert _from_proto_value(proto) == ["a", 1]

    def test_dict_value(self, mock_grpc: dict[str, Any]) -> None:
        from ojs.transport.grpc import _from_proto_value, _to_proto_value

        proto = _to_proto_value({"key": "val"})
        assert proto == {"struct_value": {"fields": {"key": {"string_value": "val"}}}}
        assert _from_proto_value(proto) == {"key": "val"}


class TestProtobufCodec:
    def test_enqueue_request_uses_protobuf_wire_bytes(self) -> None:
        codec = ProtobufCodec()
        payload = codec.encode_request(
            "Enqueue",
            {"type": "email.send", "args": ["user@example.com"]},
        )

        assert payload
        assert not payload.startswith(b"{")
        request = job_pb2.EnqueueRequest.FromString(payload)
        assert request.type == "email.send"
        assert request.args[0].string_value == "user@example.com"

    def test_response_round_trip(self) -> None:
        codec = ProtobufCodec()
        response = job_pb2.EnqueueResponse(
            job=job_pb2.Job(
                id="job-1",
                type="email.send",
                state=job_pb2.JOB_STATE_AVAILABLE,
            )
        )

        decoded = codec.decode_response("Enqueue", response.SerializeToString())

        assert decoded["job"]["id"] == "job-1"
        assert decoded["job"]["state"] == "JOB_STATE_AVAILABLE"

    def test_int64_response_fields_remain_integers(self) -> None:
        response = queue_pb2.QueueStatsResponse(
            queue="critical",
            stats=queue_pb2.QueueStatistics(
                available=2**40,
                active=4,
            ),
        )

        decoded = ProtobufCodec.response_dict(response)

        assert decoded["stats"]["available"] == 2**40
        assert isinstance(decoded["stats"]["available"], int)

    def test_invalid_payload_never_falls_back_to_json(self) -> None:
        codec = ProtobufCodec()

        with pytest.raises(ProtobufCodecError):
            codec.encode_request("Enqueue", {"type": {"not": "a string"}})

    async def test_unary_stub_interoperates_with_generated_messages(self) -> None:
        channel = ProtobufRoundTripChannel()
        stub = GrpcUnaryStub(channel)

        response = await stub.call(
            "Enqueue",
            {"type": "email.send", "args": [{"to": "user@example.com"}]},
            timeout=2.0,
            metadata=(("x-test", "value"),),
        )

        assert channel.request_bytes
        assert not channel.request_bytes.startswith(b"{")
        assert response["job"]["args"] == [{"to": "user@example.com"}]


class TestGrpcProjections:
    def test_projects_every_enqueue_option(self) -> None:
        request = project_enqueue(
            {
                "type": "email.send",
                "args": [{"to": "user@example.com"}],
                "meta": {"trace_id": "trace-1", "encrypted": True},
                "options": {
                    "queue": "email",
                    "priority": 10,
                    "timeout_ms": 1500,
                    "delay_until": "2026-01-01T00:00:05Z",
                    "expires_at": "2026-01-01T00:01:00Z",
                    "retry": {
                        "max_attempts": 5,
                        "initial_interval": "PT2S",
                        "backoff_coefficient": 2.5,
                        "max_interval": "PT1M",
                        "jitter": False,
                        "non_retryable_errors": ["InvalidInput"],
                    },
                    "unique": {
                        "key": ["type", "args", "meta"],
                        "args_keys": ["to"],
                        "meta_keys": ["tenant"],
                        "period": "PT5M",
                        "states": ["available", "active"],
                        "on_conflict": "replace",
                    },
                    "tags": ["urgent"],
                },
            },
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

        options = request["options"]
        assert options["queue"] == "email"
        assert options["priority"] == 10
        assert options["timeout"] == "1.5s"
        assert options["ttl"] == "60s"
        assert options["meta"]["encrypted"] is True
        assert options["trace_id"] == "trace-1"
        assert options["retry"]["initial_interval"] == "2s"
        assert options["retry"]["max_interval"] == "60s"
        assert options["unique"]["args_keys"] == ["to"]
        assert options["unique"]["meta_keys"] == ["tenant"]

        encoded = ProtobufCodec().encode_request("Enqueue", request)
        decoded = job_pb2.EnqueueRequest.FromString(encoded)
        assert decoded.options.timeout.seconds == 1
        assert decoded.options.timeout.nanos == 500_000_000
        assert decoded.options.unique.args_keys == ["to"]
        assert decoded.options.unique.meta_keys == ["tenant"]

    def test_schema_enqueue_fails_instead_of_dropping_field(self) -> None:
        with pytest.raises(ojs.OJSCapabilityError, match="no schema field"):
            project_enqueue(
                {
                    "type": "email.send",
                    "args": [],
                    "schema": "urn:ojs:schema:email.send:v1",
                }
            )

    def test_projects_complete_job_envelope(self) -> None:
        projected = project_job(
            {
                "id": "job-1",
                "type": "email.send",
                "queue": "email",
                "args": [{"to": "user@example.com"}],
                "meta": {"ojs.codec.encodings": ["binary/encrypted"]},
                "state": "JOB_STATE_COMPLETED",
                "priority": 10,
                "attempt": 2,
                "max_attempts": 5,
                "retry_policy": {
                    "max_attempts": 5,
                    "initial_interval": "2s",
                    "backoff_coefficient": 2.0,
                    "max_interval": "60s",
                    "jitter": True,
                    "non_retryable_errors": ["InvalidInput"],
                },
                "unique_policy": {
                    "key": ["type", "args"],
                    "period": "300s",
                    "on_conflict": "UNIQUE_CONFLICT_ACTION_REJECT",
                    "states": ["JOB_STATE_AVAILABLE"],
                    "args_keys": ["to"],
                    "meta_keys": ["tenant"],
                },
                "timeout": "1.5s",
                "created_at": "2026-01-01T00:00:00Z",
                "enqueued_at": "2026-01-01T00:00:01Z",
                "started_at": "2026-01-01T00:00:02Z",
                "completed_at": "2026-01-01T00:00:03Z",
                "scheduled_at": "2026-01-01T00:00:01Z",
                "expires_at": "2026-01-01T01:00:00Z",
                "tags": ["urgent"],
                "result": {"sent": True},
                "errors": [
                    {
                        "code": "Transient",
                        "message": "retry",
                        "retryable": True,
                        "attempt": 1,
                    }
                ],
            }
        )
        job = ojs.Job.from_dict(projected)

        assert job.state is ojs.JobState.COMPLETED
        assert job.meta["ojs.codec.encodings"] == ["binary/encrypted"]
        assert job.timeout_ms == 1500
        assert job.retry is not None
        assert job.retry.initial_interval == "PT2S"
        assert job.unique is not None
        assert job.unique.args_keys == ["to"]
        assert job.unique.meta_keys == ["tenant"]
        assert job.result == {"sent": True}
        assert job.errors[0]["code"] == "Transient"

    def test_explicit_false_retry_jitter_survives_projection(self) -> None:
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                retry_policy=job_pb2.RetryPolicy(jitter=False),
            )
        )

        assert projected["retry"]["jitter"] is False

    def test_explicit_zero_retry_max_attempts_survives_projection(self) -> None:
        """OJS-PY-047 regression: explicit 0 must not become the default 3.

        ``RetryPolicy.max_attempts`` is a presence-less proto3 scalar field,
        so ``MessageToDict`` omits it by default when it holds its zero
        value, indistinguishable from the field never being touched. Before
        the fix, ``job_projection`` would then substitute a hardcoded
        default of 3, silently turning an explicit "no retries" policy into
        "retry up to 3 times".
        """
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                retry_policy=job_pb2.RetryPolicy(max_attempts=0),
            )
        )

        assert projected["retry"]["max_attempts"] == 0
        job = ojs.Job.from_dict(projected)
        assert job.retry is not None
        assert job.retry.max_attempts == 0

    def test_explicit_zero_backoff_coefficient_survives_projection(self) -> None:
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                retry_policy=job_pb2.RetryPolicy(backoff_coefficient=0.0),
            )
        )

        assert projected["retry"]["backoff_coefficient"] == 0.0
        job = ojs.Job.from_dict(projected)
        assert job.retry is not None
        assert job.retry.backoff_coefficient == 0.0

    def test_explicit_zero_job_level_max_attempts_survives_projection(self) -> None:
        """The Job-level ``max_attempts`` mirrors the same presence pitfall."""
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                max_attempts=0,
            )
        )

        assert projected["max_attempts"] == 0
        job = ojs.Job.from_dict(projected)
        assert job.max_attempts == 0

    def test_absent_retry_policy_submessage_projects_no_retry_key(self) -> None:
        """Presence, not zero-omission, decides whether ``retry`` appears.

        When the ``retry_policy`` submessage itself was never set (a real
        presence signal: message-typed fields always track ``HasField``,
        unlike the flat scalar fields inside them), the projection must
        leave ``retry`` out entirely so ``Job.from_dict`` applies the SDK's
        own ``RetryPolicy`` default, instead of fabricating a retry policy
        from zero-valued fields that were never actually configured.
        """
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
            )
        )

        assert "retry" not in projected
        job = ojs.Job.from_dict(projected)
        assert job.retry is None

    def test_dict_source_missing_max_attempts_key_falls_back_to_sdk_default(
        self,
    ) -> None:
        """A plain mapping (not a protobuf message) can genuinely omit a key.

        Only protobuf messages are guaranteed to report every presence-less
        scalar field once extracted via ``_mapping``. A hand-built mapping
        that simply never includes ``max_attempts`` still defers to
        ``Job``'s own default of 3, since there is no zero value to
        preserve when the key is absent altogether.
        """
        projected = project_job({"id": "job-1", "type": "task.run", "state": "available"})

        assert "max_attempts" not in projected
        job = ojs.Job.from_dict(projected)
        assert job.max_attempts == 3

    def test_protobuf_message_without_explicit_max_attempts_reports_wire_zero(
        self,
    ) -> None:
        """Document the residual ambiguity for the flat, presence-less field.

        ``Job.max_attempts`` (unlike ``retry_policy``) has no presence
        tracking of its own, so a protobuf ``Job`` that never touches it is
        wire-identical to one that explicitly requests zero attempts. The
        fix trusts the wire value in both cases rather than guessing that
        the caller "must have meant" the SDK default of 3.
        """
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
            )
        )

        assert projected["max_attempts"] == 0

    def test_unspecified_job_state_maps_to_available_not_literal_string(self) -> None:
        """JOB_STATE_UNSPECIFIED is a real "not specified" sentinel.

        Unlike ``max_attempts``/``backoff_coefficient``, an unspecified
        enum is not itself meaningful data and must still resolve to the
        SDK's default state instead of leaking through as an invalid
        ``"unspecified"`` job state once zero-valued enums are no longer
        omitted from the projection.
        """
        projected = project_job(
            job_pb2.Job(id="job-1", type="task.run", state=job_pb2.JOB_STATE_UNSPECIFIED)
        )

        assert projected["state"] == "available"
        job = ojs.Job.from_dict(projected)
        assert job.state is ojs.JobState.AVAILABLE

    def test_absent_queue_still_falls_back_to_default(self) -> None:
        projected = project_job(
            job_pb2.Job(id="job-1", type="task.run", state=job_pb2.JOB_STATE_AVAILABLE)
        )

        assert projected["queue"] == "default"

    def test_absent_unique_policy_key_lists_remain_none_not_empty(self) -> None:
        """Repeated fields carry no presence: an absent list stays ``None``.

        Unlike ``max_attempts``, an explicitly-empty repeated field and an
        untouched one are wire-identical, so ``args_keys``/``meta_keys``
        must still defer to ``UniquePolicy``'s ``None`` default (meaning
        "no restriction") rather than always projecting an empty list (which
        would instead mean "restricted to nothing").
        """
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                unique_policy=job_pb2.UniquePolicy(key=["type"]),
            )
        )

        assert "args_keys" not in projected["unique"]
        assert "meta_keys" not in projected["unique"]
        job = ojs.Job.from_dict(projected)
        assert job.unique is not None
        assert job.unique.args_keys is None
        assert job.unique.meta_keys is None

    def test_explicit_unique_policy_key_lists_survive_projection(self) -> None:
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                unique_policy=job_pb2.UniquePolicy(
                    args_keys=["to"],
                    meta_keys=["tenant"],
                ),
            )
        )

        assert projected["unique"]["args_keys"] == ["to"]
        assert projected["unique"]["meta_keys"] == ["tenant"]

    def test_negative_priority_survives_projection(self) -> None:
        """Sanity check: non-zero explicit values were never at risk, but a
        negative value exercises the same code path as zero without being
        the protobuf zero value itself."""
        projected = project_job(
            job_pb2.Job(
                id="job-1",
                type="task.run",
                state=job_pb2.JOB_STATE_AVAILABLE,
                priority=-5,
            )
        )

        assert projected["priority"] == -5

    async def test_heartbeat_extends_every_active_job(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            side_effect=[
                {"directed_state": "WORKER_STATE_RUNNING"},
                {"directed_state": "WORKER_STATE_QUIET"},
                {"directed_state": "WORKER_STATE_RUNNING"},
            ]
        )

        response = await transport.heartbeat(
            "worker-1",
            ["job-1", "job-2", "job-3"],
            45_000,
        )

        assert response == {
            "state": "quiet",
            "jobs_extended": ["job-1", "job-2", "job-3"],
        }
        calls = transport._stub.call.await_args_list
        assert [call.args[1]["id"] for call in calls] == [
            "job-1",
            "job-2",
            "job-3",
        ]
        assert all(call.args[1]["extend_by"] == "45s" for call in calls)

    async def test_custom_fetch_visibility_timeout_is_not_silently_dropped(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)

        with pytest.raises(ojs.OJSCapabilityError, match="custom visibility timeout"):
            await transport.fetch(["default"], visibility_timeout_ms=60_000)

    async def test_list_queues_follows_all_cursors(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            side_effect=[
                {
                    "queues": [{"name": "first", "paused": False}],
                    "next_cursor": "page-2",
                },
                {
                    "queues": [{"name": "second", "paused": True}],
                    "next_cursor": "",
                },
            ]
        )

        queues = await transport.list_queues()

        assert [queue.name for queue in queues] == ["first", "second"]
        assert transport._stub.call.await_args_list[1].args[1]["cursor"] == "page-2"

    async def test_register_cron_projects_execution_options(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(return_value={"name": "daily"})

        await transport.register_cron_job(
            {
                "name": "daily",
                "cron": "0 0 * * *",
                "type": "task.run",
                "args": [1],
                "meta": {"tenant": "acme"},
                "options": {
                    "queue": "critical",
                    "priority": 9,
                    "tags": ["daily"],
                    "retry": {"max_attempts": 5, "jitter": False},
                },
            }
        )

        request = transport._stub.call.await_args.args[1]
        assert request["options"]["queue"] == "critical"
        assert request["options"]["priority"] == 9
        assert request["options"]["tags"] == ["daily"]
        assert request["options"]["meta"] == {"tenant": "acme"}
        assert request["options"]["retry"]["jitter"] is False

    async def test_workflow_projects_options_and_metadata(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            return_value={
                "workflow": {
                    "id": "wf-1",
                    "name": "projected",
                    "state": "WORKFLOW_STATE_RUNNING",
                }
            }
        )
        definition = ojs.chain(
            "projected",
            [
                ojs.JobRequest(
                    type="task.run",
                    args=[1],
                    queue="critical",
                    meta={"trace_id": "trace-1"},
                    priority=9,
                    timeout_ms=1500,
                    tags=["workflow"],
                )
            ],
        )

        await transport.create_workflow(definition)

        request = transport._stub.call.await_args.args[1]
        options = request["steps"][0]["options"]
        assert options["queue"] == "critical"
        assert options["priority"] == 9
        assert options["timeout"] == "1.5s"
        assert options["meta"] == {"trace_id": "trace-1"}
        assert options["tags"] == ["workflow"]

    async def test_unrepresentable_workflow_fails_before_rpc(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock()
        schema_definition = ojs.chain(
            "schema",
            [ojs.JobRequest(type="task.run", schema="task.v1")],
        )
        callback_definition = ojs.batch(
            "batch",
            [ojs.JobRequest(type="task.run")],
            on_failure=ojs.JobRequest(type="task.failed"),
        )

        with pytest.raises(ojs.OJSCapabilityError, match="no schema field"):
            await transport.create_workflow(schema_definition)
        with pytest.raises(ojs.OJSCapabilityError, match="batch callbacks"):
            await transport.create_workflow(callback_definition)

        transport._stub.call.assert_not_awaited()


class TestGrpcCapabilitiesAndPaging:
    async def test_unsupported_calls_raise_without_rpc(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock()

        operations = (
            transport.progress({"job_id": "job-1", "progress": 50}),
            transport.list_schemas(),
            transport.register_schema({"uri": "schema:v1"}),
            transport.get_schema("schema:v1"),
            transport.delete_schema("schema:v1"),
            transport.request("GET", "/checkpoints/job-1"),
        )
        for operation in operations:
            with pytest.raises(ojs.OJSCapabilityError):
                await operation

        transport._stub.call.assert_not_awaited()

    async def test_dead_letter_offset_follows_backend_cursor(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            side_effect=[
                {
                    "jobs": [
                        {"id": "job-0", "type": "task", "state": "JOB_STATE_DISCARDED"},
                        {"id": "job-1", "type": "task", "state": "JOB_STATE_DISCARDED"},
                    ],
                    "total_count": 4,
                    "next_cursor": "cursor-2",
                },
                {
                    "jobs": [{"id": "job-2", "type": "task", "state": "JOB_STATE_DISCARDED"}],
                    "total_count": 4,
                    "next_cursor": "cursor-3",
                },
            ]
        )

        response = await transport.list_dead_letter_jobs(
            queue="dead",
            limit=1,
            offset=2,
        )

        assert [job["id"] for job in response["jobs"]] == ["job-2"]
        assert response["pagination"] == {
            "total": 4,
            "limit": 1,
            "offset": 2,
            "next_cursor": "cursor-3",
        }
        calls = transport._stub.call.await_args_list
        assert calls[0].args[1] == {"limit": 3, "queue": "dead"}
        assert calls[1].args[1] == {
            "limit": 1,
            "queue": "dead",
            "cursor": "cursor-2",
        }

    async def test_cron_offset_is_applied_locally(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            return_value={
                "entries": [
                    {"name": "cron-0", "cron": "* * * * *", "type": "task"},
                    {"name": "cron-1", "cron": "* * * * *", "type": "task"},
                    {"name": "cron-2", "cron": "* * * * *", "type": "task"},
                ]
            }
        )

        response = await transport.list_cron_jobs(limit=1, offset=1)

        assert [entry["name"] for entry in response["cron_jobs"]] == ["cron-1"]
        assert response["pagination"] == {"total": 3, "limit": 1, "offset": 1}

    async def test_cancel_workflow_returns_actual_rpc_workflow(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(
            return_value={
                "workflow": {
                    "id": "wf-1",
                    "name": "cancelled-workflow",
                    "state": "WORKFLOW_STATE_FAILED",
                }
            }
        )

        response = await transport.cancel_workflow("wf-1")

        assert response["state"] == "failed"

    async def test_existing_ojs_error_is_not_reclassified(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        original = ojs.OJSValidationError("invalid projection")
        transport._stub.call = AsyncMock(side_effect=original)

        with pytest.raises(ojs.OJSValidationError) as raised:
            await transport.info("job-1")

        assert raised.value is original

    async def test_rpc_time_import_error_remains_import_error(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        original = ImportError("protobuf runtime missing")
        transport._stub.call = AsyncMock(side_effect=original)

        with pytest.raises(ImportError) as raised:
            await transport.info("job-1")

        assert raised.value is original

    async def test_ack_does_not_fabricate_true_response(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        transport = _create_transport(mock_grpc)
        transport._stub.call = AsyncMock(return_value={})

        assert await transport.ack("job-1") == {"acknowledged": False}


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
        assert type(result) is ojs.OJSAPIError

    def test_structured_error_info_selects_canonical_exception(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        from google.rpc import error_details_pb2, status_pb2

        from ojs.transport.grpc import _map_grpc_error

        error_info = error_details_pb2.ErrorInfo(
            reason="QUEUE_PAUSED",
            domain="openjobspec.org",
            metadata={
                "request_id": "request-1",
                "retryable": "true",
                "queue": "critical",
            },
        )
        packed = any_pb2.Any()
        packed.Pack(error_info)
        status = status_pb2.Status(
            code=9,
            message="queue is paused",
            details=[packed],
        )
        err = FakeAioRpcError(
            FakeGrpcStatusCode.FAILED_PRECONDITION,
            "coarse message",
            trailing_metadata=(("grpc-status-details-bin", status.SerializeToString()),),
        )

        result = _map_grpc_error(err)

        assert isinstance(result, ojs.QueuePausedError)
        assert result.error.message == "queue is paused"
        assert result.error.request_id == "request-1"
        assert result.error.details["queue"] == "critical"

    def test_malformed_status_details_bin_falls_back_to_status_code_mapping(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        """OJS-PY-048 regression: a corrupt trailer must not crash the mapper.

        ``status_pb2.Status.ParseFromString`` raises
        ``google.protobuf.message.DecodeError`` (not a ``ValueError``) for a
        malformed ``grpc-status-details-bin`` trailer. Before the fix, that
        exception propagated out of ``_map_grpc_error`` uncaught instead of
        falling back to the ordinary gRPC status-code mapping.
        """
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(
            FakeGrpcStatusCode.FAILED_PRECONDITION,
            "queue paused",
            trailing_metadata=(
                ("grpc-status-details-bin", b"\xff\xff\xff not a valid protobuf message"),
            ),
        )

        result = _map_grpc_error(err)

        assert type(result) is ojs.OJSAPIError
        assert result.status_code == 422
        assert result.error.message == "queue paused"

    def test_malformed_status_details_bin_on_retryable_code_still_retryable(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        """The status-code fallback path still classifies retryability correctly."""
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(
            FakeGrpcStatusCode.UNAVAILABLE,
            "server restarting",
            trailing_metadata=(("grpc-status-details-bin", b"\x00\x01\x02garbage\xff"),),
        )

        result = _map_grpc_error(err)

        assert isinstance(result, ojs.OJSConnectionError)

    def test_truncated_status_details_bin_falls_back_gracefully(
        self,
        mock_grpc: dict[str, Any],
    ) -> None:
        """An empty/truncated trailer value is handled the same way as garbage bytes."""
        from ojs.transport.grpc import _map_grpc_error

        err = FakeAioRpcError(
            FakeGrpcStatusCode.INTERNAL,
            "internal error",
            trailing_metadata=(("grpc-status-details-bin", b"\x08"),),
        )

        result = _map_grpc_error(err)

        assert type(result) is ojs.OJSAPIError
        assert result.status_code == 500

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
