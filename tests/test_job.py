"""Tests for Job, JobRequest, JobContext, JobState, and UniquePolicy."""

from datetime import UTC, datetime

import ojs
from ojs.job import Job, JobContext, JobRequest, JobState, UniquePolicy


class TestJobState:
    def test_all_states_exist(self) -> None:
        assert JobState.SCHEDULED == "scheduled"
        assert JobState.AVAILABLE == "available"
        assert JobState.PENDING == "pending"
        assert JobState.ACTIVE == "active"
        assert JobState.COMPLETED == "completed"
        assert JobState.RETRYABLE == "retryable"
        assert JobState.CANCELLED == "cancelled"
        assert JobState.DISCARDED == "discarded"

    def test_terminal_states(self) -> None:
        assert JobState.COMPLETED.is_terminal is True
        assert JobState.CANCELLED.is_terminal is True
        assert JobState.DISCARDED.is_terminal is True

    def test_non_terminal_states(self) -> None:
        assert JobState.SCHEDULED.is_terminal is False
        assert JobState.AVAILABLE.is_terminal is False
        assert JobState.PENDING.is_terminal is False
        assert JobState.ACTIVE.is_terminal is False
        assert JobState.RETRYABLE.is_terminal is False


class TestUniquePolicy:
    def test_defaults(self) -> None:
        policy = UniquePolicy()
        assert policy.keys == ["type", "queue", "args"]
        assert policy.on_conflict == "reject"
        assert policy.states == ["available", "active", "scheduled"]
        assert policy.period is None

    def test_to_dict(self) -> None:
        policy = UniquePolicy(
            keys=["type", "args"],
            period="PT5M",
            states=["available"],
            on_conflict="replace",
        )
        d = policy.to_dict()
        assert d["key"] == ["type", "args"]
        assert d["period"] == "PT5M"
        assert d["states"] == ["available"]
        assert d["on_conflict"] == "replace"

    def test_from_dict(self) -> None:
        data = {
            "key": ["type"],
            "period": "PT10M",
            "states": ["active"],
            "on_conflict": "ignore",
        }
        policy = UniquePolicy.from_dict(data)
        assert policy.keys == ["type"]
        assert policy.period == "PT10M"
        assert policy.states == ["active"]
        assert policy.on_conflict == "ignore"

    def test_from_dict_defaults(self) -> None:
        policy = UniquePolicy.from_dict({})
        assert policy.keys == ["type", "queue", "args"]
        assert policy.on_conflict == "reject"

    def test_frozen(self) -> None:
        policy = UniquePolicy()
        import pytest
        with pytest.raises(AttributeError):
            policy.on_conflict = "replace"  # type: ignore[misc]

    def test_roundtrip(self) -> None:
        original = UniquePolicy(
            keys=["type", "queue"],
            period="PT1H",
            states=["available", "active"],
            on_conflict="reject",
        )
        restored = UniquePolicy.from_dict(original.to_dict())
        assert restored.keys == original.keys
        assert restored.period == original.period
        assert restored.states == original.states
        assert restored.on_conflict == original.on_conflict


class TestJobFromDict:
    def test_minimal_job(self) -> None:
        job = Job.from_dict({
            "id": "j-001",
            "type": "email.send",
            "state": "available",
        })
        assert job.id == "j-001"
        assert job.type == "email.send"
        assert job.state == JobState.AVAILABLE
        assert job.args == []
        assert job.queue == "default"
        assert job.priority == 0

    def test_full_job(self) -> None:
        job = Job.from_dict({
            "id": "j-002",
            "type": "report.generate",
            "state": "active",
            "args": [1, "pdf"],
            "queue": "reports",
            "meta": {"user_id": "u-123"},
            "priority": 5,
            "attempt": 2,
            "max_attempts": 5,
            "timeout_ms": 60000,
            "tags": ["urgent", "pdf"],
            "created_at": "2025-02-12T08:00:00Z",
            "enqueued_at": "2025-02-12T08:00:01Z",
            "started_at": "2025-02-12T08:00:05Z",
            "result": None,
            "errors": [{"code": "timeout", "message": "timed out"}],
        })
        assert job.state == JobState.ACTIVE
        assert job.args == [1, "pdf"]
        assert job.queue == "reports"
        assert job.meta == {"user_id": "u-123"}
        assert job.priority == 5
        assert job.attempt == 2
        assert job.max_attempts == 5
        assert job.timeout_ms == 60000
        assert job.tags == ["urgent", "pdf"]
        assert job.created_at == datetime(2025, 2, 12, 8, 0, tzinfo=UTC)
        assert job.started_at is not None
        assert len(job.errors) == 1

    def test_with_retry_policy(self) -> None:
        job = Job.from_dict({
            "id": "j-003",
            "type": "test",
            "state": "retryable",
            "retry": {
                "max_attempts": 5,
                "initial_interval": "PT2S",
                "backoff_coefficient": 3.0,
                "max_interval": "PT10M",
                "jitter": True,
            },
        })
        assert job.retry is not None
        assert job.retry.max_attempts == 5
        assert job.retry.initial_interval == "PT2S"
        assert job.retry.backoff_coefficient == 3.0

    def test_with_unique_policy(self) -> None:
        job = Job.from_dict({
            "id": "j-004",
            "type": "test",
            "state": "available",
            "unique": {
                "key": ["type", "queue"],
                "period": "PT5M",
                "on_conflict": "replace",
            },
        })
        assert job.unique is not None
        assert job.unique.keys == ["type", "queue"]
        assert job.unique.period == "PT5M"

    def test_null_optional_fields(self) -> None:
        job = Job.from_dict({
            "id": "j-005",
            "type": "test",
            "state": "available",
            "retry": None,
            "unique": None,
            "created_at": None,
            "timeout_ms": None,
        })
        assert job.retry is None
        assert job.unique is None
        assert job.created_at is None
        assert job.timeout_ms is None

    def test_datetime_parsing_with_offset(self) -> None:
        job = Job.from_dict({
            "id": "j-006",
            "type": "test",
            "state": "completed",
            "completed_at": "2025-02-12T15:30:00+05:30",
        })
        assert job.completed_at is not None
        assert job.completed_at.utcoffset() is not None


class TestJobRequest:
    def test_minimal_to_dict(self) -> None:
        req = JobRequest(type="email.send", args=["a@b.com"])
        d = req.to_dict()
        assert d["type"] == "email.send"
        assert d["args"] == ["a@b.com"]
        assert "options" not in d

    def test_with_queue(self) -> None:
        req = JobRequest(type="test", args=[], queue="email")
        d = req.to_dict()
        assert d["options"]["queue"] == "email"

    def test_default_queue_not_in_options(self) -> None:
        req = JobRequest(type="test", args=[], queue="default")
        d = req.to_dict()
        assert "options" not in d

    def test_with_all_options(self) -> None:
        req = JobRequest(
            type="report.generate",
            args=[1, 2],
            queue="reports",
            meta={"trace": "abc"},
            priority=10,
            timeout_ms=30000,
            delay_until="2025-02-12T10:00:00Z",
            expires_at="2025-02-13T10:00:00Z",
            retry=ojs.RetryPolicy(max_attempts=5),
            unique=UniquePolicy(keys=["type"], on_conflict="replace"),
            tags=["urgent"],
            schema="urn:ojs:report:v1",
        )
        d = req.to_dict()
        assert d["type"] == "report.generate"
        assert d["args"] == [1, 2]
        assert d["meta"] == {"trace": "abc"}
        assert d["schema"] == "urn:ojs:report:v1"
        opts = d["options"]
        assert opts["queue"] == "reports"
        assert opts["priority"] == 10
        assert opts["timeout_ms"] == 30000
        assert opts["delay_until"] == "2025-02-12T10:00:00Z"
        assert opts["expires_at"] == "2025-02-13T10:00:00Z"
        assert opts["tags"] == ["urgent"]
        assert "retry" in opts
        assert "unique" in opts

    def test_empty_meta_not_included(self) -> None:
        req = JobRequest(type="test", args=[], meta=None)
        d = req.to_dict()
        assert "meta" not in d

    def test_zero_priority_not_in_options(self) -> None:
        req = JobRequest(type="test", args=[], priority=0)
        d = req.to_dict()
        assert "options" not in d


class TestJobContext:
    def _make_job(self, **overrides: object) -> Job:
        defaults = {
            "id": "j-001",
            "type": "email.send",
            "state": JobState.ACTIVE,
            "args": ["a@b.com", "welcome"],
            "meta": {"trace_id": "t-123"},
            "attempt": 2,
        }
        defaults.update(overrides)
        return Job(**defaults)  # type: ignore[arg-type]

    def test_properties(self) -> None:
        job = self._make_job()
        ctx = JobContext(job=job, attempt=2)
        assert ctx.job_id == "j-001"
        assert ctx.job_type == "email.send"
        assert ctx.args == ["a@b.com", "welcome"]
        assert ctx.meta == {"trace_id": "t-123"}
        assert ctx.attempt == 2

    def test_cancellation(self) -> None:
        ctx = JobContext(job=self._make_job())
        assert ctx.is_cancelled is False
        ctx.cancel()
        assert ctx.is_cancelled is True

    def test_parent_results_default(self) -> None:
        ctx = JobContext(job=self._make_job())
        assert ctx.parent_results == []

    def test_parent_results_set(self) -> None:
        ctx = JobContext(
            job=self._make_job(),
            parent_results=[{"step1": "done"}, {"step2": "done"}],
        )
        assert len(ctx.parent_results) == 2
