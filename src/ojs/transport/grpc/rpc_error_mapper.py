"""Map canonical gRPC statuses into the OJS exception hierarchy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ojs.errors import (
    DuplicateJobError,
    JobNotFoundError,
    OJSAPIError,
    OJSConnectionError,
    OJSErrorDetail,
    OJSTimeoutError,
    RateLimitedError,
    map_error_response,
)


def map_grpc_error(error: Any) -> Exception:
    """Map a ``grpc.aio.AioRpcError`` without masking non-RPC failures."""
    import grpc

    code = error.code()
    message = error.details() or str(error)
    status_code = grpc_code_to_http_status(code)
    structured = _structured_error(error, status_code)
    if structured is not None:
        return structured

    detail = OJSErrorDetail(
        code=grpc_code_to_ojs_code(code),
        message=message,
        retryable=code
        in (
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.INTERNAL,
        ),
    )
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return OJSAPIError(status_code, detail)
    if code == grpc.StatusCode.NOT_FOUND:
        return JobNotFoundError(status_code, detail)
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return DuplicateJobError(status_code, detail)
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return RateLimitedError(status_code, detail)
    if code == grpc.StatusCode.UNAVAILABLE:
        return OJSConnectionError(f"gRPC server unavailable: {message}")
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return OJSTimeoutError(f"gRPC deadline exceeded: {message}")
    return OJSAPIError(status_code, detail)


def _structured_error(error: Any, status_code: int) -> OJSAPIError | None:
    """Decode the canonical google.rpc.Status trailer when a server provides it.

    Returns ``None`` (signalling the caller to fall back to the normal gRPC
    status-code mapping) whenever the trailer is missing, unparsable, or
    does not carry an OJS ``ErrorInfo`` detail. A malformed
    ``grpc-status-details-bin`` trailer raises
    ``google.protobuf.message.DecodeError`` from ``ParseFromString``, which
    is *not* a ``ValueError`` subclass, so it must be caught explicitly;
    letting it propagate would surface a raw protobuf decode error instead
    of the ordinary, still-actionable gRPC status mapping.
    """
    try:
        from google.protobuf.message import DecodeError
        from google.rpc import error_details_pb2, status_pb2  # type: ignore[import-untyped]
    except ImportError:
        return None

    trailing_metadata_method = getattr(error, "trailing_metadata", None)
    if not callable(trailing_metadata_method):
        return None
    trailing_metadata = trailing_metadata_method()
    if trailing_metadata is None:
        return None
    serialized_status: bytes | None = None
    for key, value in trailing_metadata:
        if key == "grpc-status-details-bin" and isinstance(value, bytes):
            serialized_status = value
            break
    if serialized_status is None:
        return None

    status = status_pb2.Status()
    try:
        status.ParseFromString(serialized_status)
    except (ValueError, DecodeError):
        return None

    error_info: error_details_pb2.ErrorInfo | None = None
    retry_info: error_details_pb2.RetryInfo | None = None
    field_violations: list[dict[str, str]] = []
    for detail in status.details:
        if detail.Is(error_details_pb2.ErrorInfo.DESCRIPTOR):
            unpacked = error_details_pb2.ErrorInfo()
            detail.Unpack(unpacked)
            if unpacked.domain == "openjobspec.org":
                error_info = unpacked
        elif detail.Is(error_details_pb2.RetryInfo.DESCRIPTOR):
            unpacked_retry = error_details_pb2.RetryInfo()
            detail.Unpack(unpacked_retry)
            retry_info = unpacked_retry
        elif detail.Is(error_details_pb2.BadRequest.DESCRIPTOR):
            bad_request = error_details_pb2.BadRequest()
            detail.Unpack(bad_request)
            field_violations.extend(
                {
                    "field": violation.field,
                    "description": violation.description,
                }
                for violation in bad_request.field_violations
            )
    if error_info is None:
        return None

    metadata: Mapping[str, str] = error_info.metadata
    raw_code = error_info.reason.removeprefix("OJS_")
    details: dict[str, object] = {
        key: value for key, value in metadata.items() if key not in {"request_id", "retryable"}
    }
    if field_violations:
        details["field_violations"] = field_violations
    headers: dict[str, str] = {}
    if retry_info is not None:
        retry_after = retry_info.retry_delay.seconds + retry_info.retry_delay.nanos / 1_000_000_000
        headers["retry-after"] = str(retry_after)
    return map_error_response(
        status_code,
        {
            "error": {
                "code": raw_code,
                "message": status.message or error.details() or str(error),
                "retryable": metadata.get("retryable", "false").casefold() == "true",
                "request_id": metadata.get("request_id"),
                "details": details,
            }
        },
        headers,
    )


def grpc_code_to_ojs_code(code: Any) -> str:
    import grpc

    mapping: dict[Any, str] = {
        grpc.StatusCode.INVALID_ARGUMENT: "invalid_request",
        grpc.StatusCode.NOT_FOUND: "not_found",
        grpc.StatusCode.ALREADY_EXISTS: "duplicate",
        grpc.StatusCode.FAILED_PRECONDITION: "invalid_state_transition",
        grpc.StatusCode.RESOURCE_EXHAUSTED: "rate_limited",
        grpc.StatusCode.UNAVAILABLE: "connection_error",
        grpc.StatusCode.DEADLINE_EXCEEDED: "timeout",
        grpc.StatusCode.PERMISSION_DENIED: "permission_denied",
        grpc.StatusCode.UNAUTHENTICATED: "unauthenticated",
        grpc.StatusCode.UNIMPLEMENTED: "unimplemented",
        grpc.StatusCode.INTERNAL: "internal",
    }
    return mapping.get(code, "unknown")


def grpc_code_to_http_status(code: Any) -> int:
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


__all__ = ["grpc_code_to_http_status", "grpc_code_to_ojs_code", "map_grpc_error"]
