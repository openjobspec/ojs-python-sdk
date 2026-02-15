"""OJS job envelope and related types.

Defines the core data structures for the OJS job model:
Job, JobRequest, JobContext, JobState, UniquePolicy.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ojs._utils import parse_datetime
from ojs.retry import RetryPolicy


class JobState(enum.StrEnum):
    """The 8 OJS job lifecycle states."""

    SCHEDULED = "scheduled"
    AVAILABLE = "available"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    RETRYABLE = "retryable"
    CANCELLED = "cancelled"
    DISCARDED = "discarded"

    @property
    def is_terminal(self) -> bool:
        return self in (JobState.COMPLETED, JobState.CANCELLED, JobState.DISCARDED)


@dataclass(frozen=True)
class UniquePolicy:
    """OJS unique job / deduplication policy.

    Attributes:
        keys: Dimensions to include in the uniqueness hash (type, queue, args, meta).
        args_keys: Specific keys within args to include (if args is a list of dicts).
        meta_keys: Specific keys within meta to include.
        period: ISO 8601 duration for the uniqueness window.
        states: Job states to consider for uniqueness checking.
        on_conflict: Strategy when a duplicate is found: reject, replace, or ignore.
    """

    keys: list[str] = field(default_factory=lambda: ["type", "queue", "args"])
    args_keys: list[str] | None = None
    meta_keys: list[str] | None = None
    period: str | None = None
    states: list[str] = field(
        default_factory=lambda: ["available", "active", "scheduled"]
    )
    on_conflict: str = "reject"

    def to_dict(self) -> dict:
        d: dict = {"on_conflict": self.on_conflict}
        if self.keys:
            d["key"] = self.keys
        if self.period:
            d["period"] = self.period
        if self.states:
            d["states"] = self.states
        return d

    @classmethod
    def from_dict(cls, data: dict) -> UniquePolicy:
        return cls(
            keys=data.get("key", ["type", "queue", "args"]),
            period=data.get("period"),
            states=data.get("states", ["available", "active", "scheduled"]),
            on_conflict=data.get("on_conflict", "reject"),
        )


@dataclass
class Job:
    """A fully-materialized OJS job envelope as returned by the server.

    Contains both client-provided and system-managed fields.
    """

    id: str
    type: str
    state: JobState
    args: list[Any] = field(default_factory=list)
    queue: str = "default"
    meta: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    attempt: int = 0
    max_attempts: int = 3
    timeout_ms: int | None = None
    tags: list[str] = field(default_factory=list)
    retry: RetryPolicy | None = None
    unique: UniquePolicy | None = None

    # System-managed timestamps
    created_at: datetime | None = None
    enqueued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    scheduled_at: datetime | None = None
    expires_at: datetime | None = None

    # Result / error data
    result: Any = None
    errors: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Deserialize a Job from an OJS JSON response."""
        retry = None
        if "retry" in data and data["retry"]:
            retry = RetryPolicy.from_dict(data["retry"])

        unique = None
        if "unique" in data and data["unique"]:
            unique = UniquePolicy.from_dict(data["unique"])

        return cls(
            id=data["id"],
            type=data["type"],
            state=JobState(data.get("state", "available")),
            args=data.get("args", []),
            queue=data.get("queue", "default"),
            meta=data.get("meta", {}),
            priority=data.get("priority", 0),
            attempt=data.get("attempt", 0),
            max_attempts=data.get("max_attempts", 3),
            timeout_ms=data.get("timeout_ms"),
            tags=data.get("tags", []),
            retry=retry,
            unique=unique,
            created_at=parse_datetime(data.get("created_at")),
            enqueued_at=parse_datetime(data.get("enqueued_at")),
            started_at=parse_datetime(data.get("started_at")),
            completed_at=parse_datetime(data.get("completed_at")),
            scheduled_at=parse_datetime(data.get("scheduled_at")),
            expires_at=parse_datetime(data.get("expires_at")),
            result=data.get("result"),
            errors=data.get("errors", []),
        )


@dataclass
class JobRequest:
    """A job enqueue request (client-side, before server assigns ID/state).

    Used for batch enqueue operations.
    """

    type: str
    args: list[Any] = field(default_factory=list)
    queue: str = "default"
    meta: dict[str, Any] | None = None
    priority: int = 0
    timeout_ms: int | None = None
    delay_until: str | None = None
    expires_at: str | None = None
    retry: RetryPolicy | None = None
    unique: UniquePolicy | None = None
    tags: list[str] | None = None
    schema: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the OJS HTTP enqueue request format."""
        body: dict[str, Any] = {
            "type": self.type,
            "args": self.args,
        }
        if self.meta:
            body["meta"] = self.meta
        if self.schema:
            body["schema"] = self.schema

        options: dict[str, Any] = {}
        if self.queue != "default":
            options["queue"] = self.queue
        if self.priority:
            options["priority"] = self.priority
        if self.timeout_ms is not None:
            options["timeout_ms"] = self.timeout_ms
        if self.delay_until:
            options["delay_until"] = self.delay_until
        if self.expires_at:
            options["expires_at"] = self.expires_at
        if self.retry:
            options["retry"] = self.retry.to_dict()
        if self.unique:
            options["unique"] = self.unique.to_dict()
        if self.tags:
            options["tags"] = self.tags

        if options:
            body["options"] = options

        return body


# Type alias for a job handler function
JobHandler = Callable[["JobContext"], Coroutine[Any, Any, Any]]


@dataclass
class JobContext:
    """Context passed to job handlers during execution.

    Provides access to the job data and helper methods for
    interacting with the OJS server from within a handler.
    """

    job: Job
    attempt: int = 1
    parent_results: list[Any] = field(default_factory=list)
    _cancelled: bool = False

    @property
    def job_id(self) -> str:
        return self.job.id

    @property
    def job_type(self) -> str:
        return self.job.type

    @property
    def args(self) -> list[Any]:
        return self.job.args

    @property
    def meta(self) -> dict[str, Any]:
        return self.job.meta

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        """Mark this job execution as cancelled (checked by the worker)."""
        self._cancelled = True
