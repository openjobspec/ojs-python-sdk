"""Descriptor discovery and validation for the OJS gRPC service."""

from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.descriptor import MethodDescriptor, ServiceDescriptor
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass

from ojs._generated.ojs.v1 import (
    events_pb2,
    job_pb2,
    ml_resources_pb2,
    queue_pb2,
    service_pb2,
    worker_pb2,
    workflow_pb2,
)

_REGISTERED_MODULES = (
    events_pb2,
    job_pb2,
    ml_resources_pb2,
    queue_pb2,
    service_pb2,
    worker_pb2,
    workflow_pb2,
)
_REQUIRED_UNARY_METHODS = frozenset(
    {
        "Ack",
        "CancelJob",
        "CancelWorkflow",
        "CreateWorkflow",
        "DeleteCheckpoint",
        "DeleteDeadLetter",
        "Enqueue",
        "EnqueueBatch",
        "Fetch",
        "GetCheckpoint",
        "GetJob",
        "GetWorkflow",
        "Health",
        "Heartbeat",
        "ListCron",
        "ListDeadLetter",
        "ListQueues",
        "Manifest",
        "Nack",
        "PauseQueue",
        "QueueStats",
        "RegisterCron",
        "ResumeQueue",
        "RetryDeadLetter",
        "SaveCheckpoint",
        "UnregisterCron",
    }
)


class DescriptorRegistryError(RuntimeError):
    """Required generated protobuf descriptors are missing or invalid."""


@dataclass(frozen=True)
class RpcDescriptor:
    """Message types and streaming shape for one RPC."""

    request_type: type[Message]
    response_type: type[Message]
    client_streaming: bool
    server_streaming: bool


class DescriptorRegistry:
    """Validated descriptor registry for the canonical OJS v1 service."""

    def __init__(self, service: ServiceDescriptor | None = None) -> None:
        resolved_service = service or service_pb2.DESCRIPTOR.services_by_name.get("OJSService")
        if resolved_service is None:
            raise DescriptorRegistryError(
                "Generated OJSService descriptor is missing. Reinstall the SDK "
                "with the 'grpc' extra."
            )
        self._service: ServiceDescriptor = resolved_service
        self._methods = {
            method.name: self._rpc_descriptor(method) for method in self._service.methods
        }
        self.validate()

    @staticmethod
    def _rpc_descriptor(method: MethodDescriptor) -> RpcDescriptor:
        return RpcDescriptor(
            request_type=GetMessageClass(method.input_type),
            response_type=GetMessageClass(method.output_type),
            client_streaming=method.client_streaming,
            server_streaming=method.server_streaming,
        )

    @property
    def service_name(self) -> str:
        return self._service.full_name

    def validate(self) -> None:
        """Fail before network I/O when any service method is unusable."""
        if not self._methods:
            raise DescriptorRegistryError("Generated OJSService contains no RPC descriptors")
        missing = _REQUIRED_UNARY_METHODS.difference(self._methods)
        if missing:
            raise DescriptorRegistryError(
                "Generated OJSService is missing required RPC descriptors: "
                + ", ".join(sorted(missing))
            )
        for name, rpc in self._methods.items():
            if not issubclass(rpc.request_type, Message):
                raise DescriptorRegistryError(f"{name} request descriptor is invalid")
            if not issubclass(rpc.response_type, Message):
                raise DescriptorRegistryError(f"{name} response descriptor is invalid")

    def method(self, name: str) -> RpcDescriptor:
        try:
            return self._methods[name]
        except KeyError:
            raise DescriptorRegistryError(
                f"Generated OJSService has no RPC named {name!r}"
            ) from None


__all__ = [
    "DescriptorRegistry",
    "DescriptorRegistryError",
    "RpcDescriptor",
]
