"""Catalog-driven mapping from OJS error responses to SDK exceptions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ojs.error_codes import ErrorCodeEntry, lookup_by_canonical_code, lookup_by_code
from ojs.errors import (
    DuplicateJobError,
    JobNotFoundError,
    OJSAPIError,
    OJSErrorDetail,
    QueuePausedError,
    RateLimitedError,
)
from ojs.errors.rate_limit_headers import parse_rate_limit_headers

_LEGACY_ALIASES = {
    "duplicate": "DUPLICATE_JOB",
    "not_found": "NOT_FOUND",
    "queue_paused": "QUEUE_PAUSED",
    "rate_limited": "RATE_LIMITED",
}


def _catalog_entry(code: str) -> ErrorCodeEntry | None:
    canonical = _LEGACY_ALIASES.get(code.casefold(), code.upper())
    return lookup_by_canonical_code(canonical) or lookup_by_code(code.upper())


def _string(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _details(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if value is None:
        return {}
    return {"raw_details": value}


def _error_payload(body: Mapping[str, Any]) -> tuple[Mapping[str, Any], dict[str, Any]]:
    raw_error = body.get("error")
    if isinstance(raw_error, Mapping):
        return raw_error, {}
    if raw_error is None:
        return {}, {}
    return {}, {"raw_error": raw_error}


def map_error_response(
    status_code: int,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> OJSAPIError:
    """Build the most specific exception for an OJS error response."""
    error_data, malformed_details = _error_payload(body)
    code = _string(error_data.get("code"), "unknown")
    entry = _catalog_entry(code)
    default_message = entry.message if entry is not None else "Unknown error"
    retryable_value = error_data.get("retryable")
    retryable = (
        retryable_value
        if isinstance(retryable_value, bool)
        else entry.retryable
        if entry is not None
        else False
    )
    details = _details(error_data.get("details"))
    details.update(malformed_details)
    detail = OJSErrorDetail(
        code=code,
        message=_string(error_data.get("message"), default_message),
        retryable=retryable,
        details=details,
        request_id=(
            error_data.get("request_id") if isinstance(error_data.get("request_id"), str) else None
        ),
    )

    canonical = (
        _LEGACY_ALIASES.get(code.casefold(), code.upper())
        if entry is None
        else entry.canonical_code
    )
    if canonical == "DUPLICATE_JOB":
        return DuplicateJobError(status_code, detail)
    if canonical == "NOT_FOUND":
        return JobNotFoundError(status_code, detail)
    if canonical == "QUEUE_PAUSED":
        return QueuePausedError(status_code, detail)
    if canonical == "RATE_LIMITED" or status_code == 429:
        rate_limit = parse_rate_limit_headers(headers)
        retry_after = rate_limit.retry_after if rate_limit is not None else None
        return RateLimitedError(
            status_code,
            detail,
            retry_after=retry_after,
            rate_limit=rate_limit,
        )
    return OJSAPIError(status_code, detail)


def raise_for_error(
    status_code: int,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> None:
    """Raise the exception mapped from an OJS error response."""
    raise map_error_response(status_code, body, headers)


__all__ = ["map_error_response", "raise_for_error"]
