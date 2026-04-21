"""OJS job envelope and related types.

Defines the core data structures for the OJS job model:
Job, JobRequest, JobContext, JobState, UniquePolicy.
"""

from __future__ import annotations

import asyncio
import enum
import warnings
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from inspect import Parameter, Signature
from typing import Any, ClassVar

from ojs.errors import OJSCapabilityError, OJSValidationError
from ojs.retry import RetryPolicy
from ojs.wire_validation import WireDecoder


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
    states: list[str] = field(default_factory=lambda: ["available", "active", "scheduled"])
    on_conflict: str = "reject"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"on_conflict": self.on_conflict}
        if self.keys:
            d["key"] = self.keys
        if self.period:
            d["period"] = self.period
        if self.states:
            d["states"] = self.states
        if self.args_keys is not None:
            d["args_keys"] = list(self.args_keys)
        if self.meta_keys is not None:
            d["meta_keys"] = list(self.meta_keys)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UniquePolicy:
        return cls._from_decoder(WireDecoder.object(data, "unique"))

    @classmethod
    def _from_decoder(cls, decoder: WireDecoder) -> UniquePolicy:
        return cls(
            keys=decoder.string_array("key", ["type", "queue", "args"]),
            args_keys=(
                decoder.string_array("args_keys")
                if decoder.value("args_keys") is not None
                else None
            ),
            meta_keys=(
                decoder.string_array("meta_keys")
                if decoder.value("meta_keys") is not None
                else None
            ),
            period=decoder.string("period"),
            states=decoder.string_array(
                "states",
                ["available", "active", "scheduled"],
            ),
            on_conflict=decoder.string("on_conflict", "reject") or "reject",
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
        decoder = WireDecoder.object(data, "job")
        retry = None
        retry_data = decoder.optional_mapping("retry")
        if retry_data:
            try:
                retry = RetryPolicy.from_dict(retry_data)
            except (TypeError, ValueError) as exc:
                raise OJSValidationError(f"invalid wire value at job.retry: {exc}") from exc

        unique = None
        unique_data = decoder.optional_mapping("unique")
        if unique_data:
            unique = UniquePolicy._from_decoder(WireDecoder.object(unique_data, "job.unique"))

        state_value = decoder.string("state", "available") or "available"
        try:
            state = JobState(state_value)
        except ValueError as exc:
            raise OJSValidationError(
                f"invalid wire value at job.state: unknown job state {state_value!r}"
            ) from exc

        raw_errors = decoder.array("errors")
        errors = [
            dict(WireDecoder.object(error, f"job.errors[{index}]").data)
            for index, error in enumerate(raw_errors)
        ]

        return cls(
            id=decoder.required_string("id"),
            type=decoder.required_string("type"),
            state=state,
            args=decoder.array("args"),
            queue=decoder.string("queue", "default") or "default",
            meta=decoder.mapping("meta"),
            priority=decoder.integer("priority", 0) or 0,
            attempt=decoder.integer("attempt", 0) or 0,
            max_attempts=decoder.integer("max_attempts", 3) or 0,
            timeout_ms=decoder.integer("timeout_ms"),
            tags=decoder.string_array("tags"),
            retry=retry,
            unique=unique,
            created_at=decoder.datetime("created_at"),
            enqueued_at=decoder.datetime("enqueued_at"),
            started_at=decoder.datetime("started_at"),
            completed_at=decoder.datetime("completed_at"),
            scheduled_at=decoder.datetime("scheduled_at"),
            expires_at=decoder.datetime("expires_at"),
            result=decoder.value("result"),
            errors=errors,
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
ProgressReporter = Callable[[int, str, dict[str, Any] | None], Awaitable[None]]


@dataclass(init=False)
class JobContext:
    """Context passed to job handlers during execution.

    Provides access to the job data and helper methods for
    interacting with the OJS server from within a handler.
    """

    __signature__: ClassVar[Signature]
    job: Job
    attempt: int = 1
    parent_results: list[Any] = field(default_factory=list)
    _cancelled: bool = False
    _transport: Any = field(default=None, repr=False)
    _retry_sleep: Callable[[float], Awaitable[None]] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _lease_remaining: Callable[[], float] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _progress_reporter: ProgressReporter | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __init__(
        self,
        job: Job,
        attempt: int = 1,
        parent_results: list[Any] = list(),  # noqa: B006, C408 - API compatibility
        _cancelled: bool = False,
        _transport: Any = None,
    ) -> None:
        """Create handler-visible context state.

        Private runtime keyword arguments remain temporarily accepted so
        existing integrations keep working while migrating.
        """
        object.__setattr__(self, "job", job)
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(
            self,
            "parent_results",
            list(parent_results) if parent_results is not None else [],
        )
        object.__setattr__(self, "_cancelled", _cancelled)
        object.__setattr__(self, "_transport", _transport)
        object.__setattr__(self, "_retry_sleep", None)
        object.__setattr__(self, "_lease_remaining", None)
        object.__setattr__(self, "_progress_reporter", None)

        if _cancelled or _transport is not None:
            warnings.warn(
                "private JobContext constructor arguments are deprecated; "
                "construct JobContext with job, attempt, and parent_results only",
                DeprecationWarning,
                stacklevel=2,
            )

    def _bind_runtime(
        self,
        *,
        transport: Any = None,
        retry_sleep: Callable[[float], Awaitable[None]] | None = None,
        lease_remaining: Callable[[], float] | None = None,
        progress_reporter: ProgressReporter | None = None,
    ) -> None:
        self._transport = transport
        self._retry_sleep = retry_sleep
        self._lease_remaining = lease_remaining
        self._progress_reporter = progress_reporter

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

    @property
    def lease_remaining(self) -> float | None:
        """Seconds remaining on the active worker lease, when available."""
        if self._lease_remaining is None:
            return None
        return self._lease_remaining()

    async def sleep_before_retry(self, delay: float) -> None:
        """Sleep using the worker's lease-aware retry budget."""
        if self._retry_sleep is None:
            await asyncio.sleep(delay)
            return
        await self._retry_sleep(delay)

    async def report_progress(
        self,
        percentage: int,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Report progress for the active job through its worker runtime."""
        if self._progress_reporter is None:
            raise OJSCapabilityError(
                "progress reporting is unavailable outside an active worker execution"
            )
        await self._progress_reporter(percentage, message, data)


JobContext.__signature__ = Signature(
    [
        Parameter(
            "job",
            Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Job,
        ),
        Parameter(
            "attempt",
            Parameter.POSITIONAL_OR_KEYWORD,
            default=1,
            annotation=int,
        ),
        Parameter(
            "parent_results",
            Parameter.POSITIONAL_OR_KEYWORD,
            default=None,
            annotation=list[Any] | None,
        ),
    ]
)
