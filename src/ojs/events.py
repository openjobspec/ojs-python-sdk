"""OJS event types.

CloudEvents-inspired event envelope for job lifecycle events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Event:
    """An OJS event.

    Follows the CloudEvents-inspired envelope defined in the OJS Events spec.
    """

    event: str
    timestamp: datetime
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def job_id(self) -> str | None:
        return self.data.get("job_id")

    @property
    def job_type(self) -> str | None:
        return self.data.get("job_type") or self.data.get("type")

    @property
    def queue(self) -> str | None:
        return self.data.get("queue")

    @property
    def state(self) -> str | None:
        return self.data.get("state")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        ts = data.get("timestamp", "")
        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
        return cls(
            event=data["event"],
            timestamp=timestamp,
            data=data.get("data", {}),
        )


# Standard event type constants
class EventType:
    """Standard OJS event type constants."""

    # Core job events
    JOB_ENQUEUED = "job.enqueued"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # Extended job events
    JOB_RETRYING = "job.retrying"
    JOB_CANCELLED = "job.cancelled"
    JOB_DISCARDED = "job.discarded"
    JOB_HEARTBEAT = "job.heartbeat"
    JOB_SCHEDULED = "job.scheduled"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    # Cron events
    CRON_TRIGGERED = "cron.triggered"
    CRON_SKIPPED = "cron.skipped"

    # Worker events
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    WORKER_QUIET = "worker.quiet"


# Event handler type
EventHandler = Any  # Callable[[Event], Coroutine[Any, Any, None]]
