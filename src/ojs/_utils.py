"""Internal utilities shared across the OJS SDK."""

from __future__ import annotations

from datetime import datetime

from ojs.errors import OJSValidationError


def parse_datetime(
    val: str | None,
    *,
    path: str = "timestamp",
) -> datetime | None:
    """Parse an ISO 8601 datetime string, handling the 'Z' suffix."""
    if val is None:
        return None
    normalized = f"{val[:-1]}+00:00" if val.endswith("Z") else val
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OJSValidationError(
            f"invalid wire value at {path}: malformed ISO 8601 timestamp {val!r}"
        ) from exc
