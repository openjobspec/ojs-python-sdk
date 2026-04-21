"""OJS queue types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ojs.wire_validation import WireDecoder


@dataclass
class Queue:
    """An OJS queue."""

    name: str
    status: str = "active"
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Queue:
        decoder = WireDecoder.object(data, "queue")
        return cls(
            name=decoder.required_string("name"),
            status=decoder.string("status", "active") or "active",
            created_at=decoder.datetime("created_at"),
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
        decoder = WireDecoder.object(data, "queue_stats")
        stats = WireDecoder.object(
            decoder.value("stats", {}),
            "queue_stats.stats",
        )
        return cls(
            queue=decoder.required_string("queue"),
            status=decoder.string("status", "active") or "active",
            available=stats.integer("available", 0) or 0,
            active=stats.integer("active", 0) or 0,
            scheduled=stats.integer("scheduled", 0) or 0,
            retryable=stats.integer("retryable", 0) or 0,
            discarded=stats.integer("discarded", 0) or 0,
            completed_last_hour=stats.integer("completed_last_hour", 0) or 0,
            failed_last_hour=stats.integer("failed_last_hour", 0) or 0,
            avg_duration_ms=stats.number("avg_duration_ms"),
            avg_wait_ms=stats.number("avg_wait_ms"),
            throughput_per_second=stats.number("throughput_per_second"),
            computed_at=decoder.datetime("computed_at"),
        )
