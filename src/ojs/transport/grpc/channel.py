"""Unary channel adapter for generated OJS protobuf descriptors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ojs.transport.grpc.descriptor_registry import DescriptorRegistry
from ojs.transport.grpc.protobuf_codec import ProtobufCodec


class UnaryCallable(Protocol):
    async def __call__(
        self,
        request: bytes,
        *,
        timeout: float,  # noqa: ASYNC109
        metadata: tuple[tuple[str, str], ...] | None,
    ) -> bytes: ...


class UnaryChannel(Protocol):
    def unary_unary(
        self,
        method: str,
        *,
        request_serializer: Any,
        response_deserializer: Any,
    ) -> UnaryCallable: ...


class GrpcChannel(UnaryChannel, Protocol):
    async def close(self) -> None: ...


class GrpcUnaryStub:
    """Descriptor-backed unary RPC dispatcher."""

    def __init__(
        self,
        channel: UnaryChannel,
        registry: DescriptorRegistry | None = None,
    ) -> None:
        self._channel = channel
        self._registry = registry or DescriptorRegistry()
        self._codec = ProtobufCodec(self._registry)

    async def call(
        self,
        method: str,
        request: Mapping[str, Any],
        *,
        timeout: float = 30.0,  # noqa: ASYNC109
        metadata: tuple[tuple[str, str], ...] | None = None,
    ) -> dict[str, Any]:
        rpc_descriptor = self._registry.method(method)
        if rpc_descriptor.client_streaming or rpc_descriptor.server_streaming:
            raise ValueError(f"{method} is not a unary RPC")
        rpc = self._channel.unary_unary(
            f"/{self._registry.service_name}/{method}",
            request_serializer=_identity,
            response_deserializer=_identity,
        )
        response = await rpc(
            self._codec.encode_request(method, request),
            timeout=timeout,
            metadata=metadata,
        )
        return self._codec.decode_response(method, response)


def _identity(value: bytes) -> bytes:
    return value


__all__ = ["GrpcUnaryStub", "UnaryCallable", "UnaryChannel"]
