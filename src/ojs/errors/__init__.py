"""OJS exception hierarchy and response error mapping."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OJSErrorDetail:
    """Structured error detail from an OJS API response."""

    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None


@dataclass
class RateLimitInfo:
    """Rate-limit metadata extracted from response headers."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    retry_after: float | None = None


class OJSError(Exception):
    """Base exception for all OJS SDK errors."""


class OJSAPIError(OJSError):
    """Error returned by an OJS server."""

    def __init__(self, status_code: int, error: OJSErrorDetail) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(f"OJS API error {status_code}: [{error.code}] {error.message}")

    @property
    def retryable(self) -> bool:
        return self.error.retryable

    @property
    def code(self) -> str:
        return self.error.code


class OJSConnectionError(OJSError):
    """Failed to connect to the OJS server."""


class OJSTimeoutError(OJSError):
    """Request to the OJS server timed out."""


class JobExecutionTimeout(OJSTimeoutError):  # noqa: N818 - public API name
    """A job handler exceeded its configured execution timeout."""

    def __init__(self, timeout_seconds: float, job_id: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.job_id = job_id
        super().__init__(f"Job {job_id} timed out after {timeout_seconds}s")


class OJSValidationError(OJSError):
    """Client-side or wire-format validation failed."""


class OJSCapabilityError(OJSError):
    """The selected transport does not support a requested capability."""


class DuplicateJobError(OJSAPIError):
    """A unique job constraint was violated."""


class JobNotFoundError(OJSAPIError):
    """A requested job or resource was not found."""


class QueuePausedError(OJSAPIError):
    """The target queue is paused."""


class RateLimitedError(OJSAPIError):
    """The server rejected the request because of rate limiting."""

    def __init__(
        self,
        status_code: int,
        error: OJSErrorDetail,
        retry_after: float | None = None,
        rate_limit: RateLimitInfo | None = None,
    ) -> None:
        super().__init__(status_code, error)
        self.retry_after = retry_after
        self.rate_limit = rate_limit


def map_error_response(
    status_code: int,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> OJSAPIError:
    """Build the most specific exception for an OJS error response."""
    from ojs.errors.response_mapper import map_error_response as map_response

    return map_response(status_code, body, headers)


def raise_for_error(
    status_code: int,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> None:
    """Raise the exception mapped from an OJS error response."""
    raise map_error_response(status_code, body, headers)


__all__ = [
    "DuplicateJobError",
    "JobExecutionTimeout",
    "JobNotFoundError",
    "OJSAPIError",
    "OJSCapabilityError",
    "OJSConnectionError",
    "OJSError",
    "OJSErrorDetail",
    "OJSTimeoutError",
    "OJSValidationError",
    "QueuePausedError",
    "RateLimitInfo",
    "RateLimitedError",
    "map_error_response",
    "raise_for_error",
]
