"""OJS error types.

Maps the standard OJS error codes to Python exceptions.
"""

from __future__ import annotations

import contextlib
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
    """Rate limit metadata extracted from response headers."""

    limit: int | None = None
    """Maximum requests allowed per window (X-RateLimit-Limit)."""

    remaining: int | None = None
    """Remaining requests in current window (X-RateLimit-Remaining)."""

    reset: int | None = None
    """Unix timestamp when window resets (X-RateLimit-Reset)."""

    retry_after: float | None = None
    """Seconds to wait before retrying (Retry-After)."""


class OJSError(Exception):
    """Base exception for all OJS SDK errors."""


class OJSAPIError(OJSError):
    """Error returned by the OJS server.

    Attributes:
        status_code: HTTP status code from the server.
        error: Parsed error detail from the response body.
    """

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


class OJSValidationError(OJSError):
    """Client-side validation error before sending a request."""


class DuplicateJobError(OJSAPIError):
    """Raised when a unique job constraint is violated (409 duplicate)."""


class JobNotFoundError(OJSAPIError):
    """Raised when a job is not found (404 not_found)."""


class QueuePausedError(OJSAPIError):
    """Raised when the target queue is paused (422 queue_paused)."""


class RateLimitedError(OJSAPIError):
    """Raised when the rate limit is exceeded (429 rate_limited).

    Attributes:
        retry_after: Seconds to wait before retrying, if provided.
        rate_limit: Full rate limit metadata from response headers.
    """

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


def raise_for_error(
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> None:
    """Parse an OJS error response and raise the appropriate exception."""
    error_data = body.get("error", {})
    detail = OJSErrorDetail(
        code=error_data.get("code", "unknown"),
        message=error_data.get("message", "Unknown error"),
        retryable=error_data.get("retryable", False),
        details=error_data.get("details", {}),
        request_id=error_data.get("request_id"),
    )

    if detail.code == "duplicate":
        raise DuplicateJobError(status_code, detail)
    if detail.code == "not_found":
        raise JobNotFoundError(status_code, detail)
    if detail.code == "queue_paused":
        raise QueuePausedError(status_code, detail)
    if detail.code == "rate_limited":
        retry_after = None
        rate_limit = None
        if headers:
            raw = headers.get("retry-after")
            if raw is not None:
                with contextlib.suppress(ValueError):
                    retry_after = float(raw)
            limit_raw = headers.get("x-ratelimit-limit")
            remaining_raw = headers.get("x-ratelimit-remaining")
            reset_raw = headers.get("x-ratelimit-reset")
            if limit_raw is not None or remaining_raw is not None or reset_raw is not None or retry_after is not None:
                rl_limit = None
                rl_remaining = None
                rl_reset = None
                if limit_raw is not None:
                    with contextlib.suppress(ValueError):
                        rl_limit = int(limit_raw)
                if remaining_raw is not None:
                    with contextlib.suppress(ValueError):
                        rl_remaining = int(remaining_raw)
                if reset_raw is not None:
                    with contextlib.suppress(ValueError):
                        rl_reset = int(reset_raw)
                rate_limit = RateLimitInfo(
                    limit=rl_limit,
                    remaining=rl_remaining,
                    reset=rl_reset,
                    retry_after=retry_after,
                )
        raise RateLimitedError(status_code, detail, retry_after=retry_after, rate_limit=rate_limit)

    raise OJSAPIError(status_code, detail)
