"""OJS queue types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ojs._utils import parse_datetime


@dataclass
class Queue:
    """An OJS queue."""

    name: str
    status: str = "active"
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Queue:
        return cls(
            name=data["name"],
            status=data.get("status", "active"),
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass
class QueueStats:
    """Statistics for an OJS queue."""

    queue: str
    status: str
    available: int = 0
    active: int = 0
    scheduled: int = 0
    retryable: int = 0
    discarded: int = 0
    completed_last_hour: int = 0
    failed_last_hour: int = 0
    avg_duration_ms: float = 0.0
    avg_wait_ms: float = 0.0
    throughput_per_second: float = 0.0
    computed_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueStats:
        stats = data.get("stats", {})
        return cls(
            queue=data["queue"],
            status=data.get("status", "active"),
            available=stats.get("available", 0),
            active=stats.get("active", 0),
            scheduled=stats.get("scheduled", 0),
            retryable=stats.get("retryable", 0),
            discarded=stats.get("discarded", 0),
            completed_last_hour=stats.get("completed_last_hour", 0),
            failed_last_hour=stats.get("failed_last_hour", 0),
            avg_duration_ms=stats.get("avg_duration_ms", 0.0),
            avg_wait_ms=stats.get("avg_wait_ms", 0.0),
            throughput_per_second=stats.get("throughput_per_second", 0.0),
            computed_at=parse_datetime(data.get("computed_at")),
        )
