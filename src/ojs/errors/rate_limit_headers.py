"""Parsing for standard HTTP rate-limit response headers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite

from ojs.errors import RateLimitInfo


def _header(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == expected),
        None,
    )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_retry_after(
    value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse Retry-After delta-seconds or an RFC 9110 HTTP date."""
    if value is None:
        return None

    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        seconds = (retry_at - current).total_seconds()

    if not isfinite(seconds):
        return None
    return max(0.0, seconds)


def parse_rate_limit_headers(
    headers: Mapping[str, str] | None,
    *,
    now: datetime | None = None,
) -> RateLimitInfo | None:
    """Return parsed rate-limit metadata, or ``None`` when absent."""
    if not headers:
        return None

    retry_after = parse_retry_after(_header(headers, "Retry-After"), now=now)
    limit = _parse_int(_header(headers, "X-RateLimit-Limit"))
    remaining = _parse_int(_header(headers, "X-RateLimit-Remaining"))
    reset = _parse_int(_header(headers, "X-RateLimit-Reset"))
    if all(value is None for value in (limit, remaining, reset, retry_after)):
        return None
    return RateLimitInfo(
        limit=limit,
        remaining=remaining,
        reset=reset,
        retry_after=retry_after,
    )


__all__ = ["parse_rate_limit_headers", "parse_retry_after"]
