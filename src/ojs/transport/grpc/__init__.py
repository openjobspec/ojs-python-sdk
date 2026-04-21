"""Lazy gRPC transport facade.

The package itself remains importable in base installations. Accessing a
gRPC implementation symbol reports the exact optional extra when grpcio or
protobuf support is unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ojs.transport.grpc.transport import GrpcTransport as GrpcTransport

_TRANSPORT_EXPORTS = frozenset(
    {
        "GrpcTransport",
        "_build_enqueue_options",
        "_dict_to_proto_bytes",
        "_from_proto_job",
        "_from_proto_value",
        "_from_proto_workflow",
        "_grpc_code_to_http_status",
        "_grpc_code_to_ojs_code",
        "_map_grpc_error",
        "_map_job_state",
        "_proto_bytes_to_dict",
        "_to_proto_value",
    }
)

__all__ = sorted(_TRANSPORT_EXPORTS)


def __getattr__(name: str) -> object:
    if name not in _TRANSPORT_EXPORTS:
        raise AttributeError(f"module 'ojs.transport.grpc' has no attribute {name!r}")
    try:
        value = getattr(import_module("ojs.transport.grpc.transport"), name)
    except ModuleNotFoundError as exc:
        if exc.name == "grpc" or (exc.name or "").startswith(
            ("google", "google.protobuf", "google.rpc")
        ):
            raise ImportError(
                "gRPC transport dependencies are required. "
                "Install with: pip install openjobspec[grpc]"
            ) from exc
        raise
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | _TRANSPORT_EXPORTS)
