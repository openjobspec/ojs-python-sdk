"""Conversions between OJS ISO values and protobuf JSON time values."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
_PROTO_DURATION = re.compile(r"^(?P<seconds>-?\d+)(?P<fraction>\.\d{1,9})?s$")


def milliseconds_to_duration(milliseconds: int) -> str:
    if milliseconds < 0:
        raise ValueError("duration milliseconds must be non-negative")
    seconds = Decimal(milliseconds) / Decimal(1000)
    return _decimal_duration(seconds)


def duration_to_milliseconds(value: str) -> int:
    match = _PROTO_DURATION.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid protobuf duration: {value!r}")
    seconds = Decimal(match.group("seconds"))
    fraction = Decimal(match.group("fraction") or "0")
    return int((seconds + fraction) * 1000)


def iso_duration_to_protobuf(value: str) -> str:
    match = _ISO_DURATION.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid ISO 8601 duration: {value!r}")
    seconds = (
        Decimal(match.group("days") or 0) * 86400
        + Decimal(match.group("hours") or 0) * 3600
        + Decimal(match.group("minutes") or 0) * 60
        + Decimal(match.group("seconds") or 0)
    )
    return _decimal_duration(seconds)


def protobuf_duration_to_iso(value: str) -> str:
    milliseconds = duration_to_milliseconds(value)
    seconds = Decimal(milliseconds) / 1000
    if seconds == seconds.to_integral():
        return f"PT{int(seconds)}S"
    return f"PT{format(seconds.normalize(), 'f')}S"


def expiry_to_ttl(
    expires_at: str,
    *,
    now: datetime | None = None,
) -> str:
    expiry = datetime.fromisoformat(
        expires_at[:-1] + "+00:00" if expires_at.endswith("Z") else expires_at
    )
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    remaining = max(Decimal(0), Decimal(str((expiry - current).total_seconds())))
    return _decimal_duration(remaining)


def _decimal_duration(seconds: Decimal) -> str:
    normalized = format(seconds.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return f"{normalized or '0'}s"


__all__ = [
    "duration_to_milliseconds",
    "expiry_to_ttl",
    "iso_duration_to_protobuf",
    "milliseconds_to_duration",
    "protobuf_duration_to_iso",
]
