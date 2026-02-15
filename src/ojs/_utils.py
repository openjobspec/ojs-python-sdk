"""Internal utilities shared across the OJS SDK."""

from __future__ import annotations

from datetime import datetime


def parse_datetime(val: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string, handling the 'Z' suffix."""
    if val is None:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))
