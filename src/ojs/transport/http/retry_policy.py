"""Operation-aware retry classification for the HTTP transport."""

from __future__ import annotations

from enum import Enum

from ojs.transport.rate_limiter import RetryConfig

_TRANSIENT_SERVER_STATUSES = frozenset({502, 503, 504})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_IDEMPOTENT_METHODS = frozenset({"DELETE", "PUT"})


class OperationSafety(Enum):
    """Replay safety of an HTTP operation."""

    SAFE = "safe"
    IDEMPOTENT = "idempotent"
    UNSAFE = "unsafe"


class RetryReason(Enum):
    """Reason a response is eligible for another attempt."""

    RATE_LIMITED = "rate_limited"
    TRANSIENT_SERVER_ERROR = "transient_server_error"


def classify_operation(
    method: str,
    *,
    idempotency_key: str | None = None,
) -> OperationSafety:
    """Classify replay safety from HTTP semantics and protocol identity."""
    normalized = method.upper()
    if normalized in _SAFE_METHODS:
        return OperationSafety.SAFE
    if normalized in _IDEMPOTENT_METHODS or idempotency_key is not None:
        return OperationSafety.IDEMPOTENT
    return OperationSafety.UNSAFE


def retry_reason(
    status_code: int,
    *,
    attempt: int,
    safety: OperationSafety,
    config: RetryConfig,
) -> RetryReason | None:
    """Return why a response should be retried within the logical budget."""
    if not config.enabled or attempt >= config.max_retries:
        return None
    if status_code == 429:
        return RetryReason.RATE_LIMITED
    if (
        status_code in _TRANSIENT_SERVER_STATUSES
        and config.retry_server_errors
        and safety is not OperationSafety.UNSAFE
    ):
        return RetryReason.TRANSIENT_SERVER_ERROR
    return None


__all__ = [
    "OperationSafety",
    "RetryReason",
    "classify_operation",
    "retry_reason",
]
