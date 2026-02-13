"""Tests for Event, EventType, Queue, and QueueStats types."""

from datetime import UTC, datetime

from ojs.events import Event, EventType
from ojs.queue import Queue, QueueStats


class TestEvent:
    def test_from_dict_with_utc_timestamp(self) -> None:
        event = Event.from_dict({
            "event": "job.completed",
            "timestamp": "2025-02-12T10:30:00Z",
            "data": {
                "job_id": "j-001",
                "job_type": "email.send",
                "queue": "default",
                "state": "completed",
            },
        })
        assert event.event == "job.completed"
        assert event.timestamp == datetime(2025, 2, 12, 10, 30, tzinfo=UTC)
        assert event.job_id == "j-001"
        assert event.job_type == "email.send"
        assert event.queue == "default"
        assert event.state == "completed"

    def test_from_dict_with_offset_timestamp(self) -> None:
        event = Event.from_dict({
            "event": "job.started",
            "timestamp": "2025-02-12T10:30:00+05:00",
            "data": {},
        })
        assert event.timestamp.utcoffset() is not None
        assert event.timestamp.utcoffset().total_seconds() == 5 * 3600

    def test_from_dict_empty_data(self) -> None:
        event = Event.from_dict({
            "event": "worker.started",
            "timestamp": "2025-01-01T00:00:00Z",
        })
        assert event.data == {}
        assert event.job_id is None
        assert event.job_type is None
        assert event.queue is None
        assert event.state is None

    def test_job_type_fallback_to_type_key(self) -> None:
        event = Event.from_dict({
            "event": "job.enqueued",
            "timestamp": "2025-01-01T00:00:00Z",
            "data": {"type": "notification.push"},
        })
        assert event.job_type == "notification.push"

    def test_job_type_prefers_job_type_over_type(self) -> None:
        event = Event.from_dict({
            "event": "job.enqueued",
            "timestamp": "2025-01-01T00:00:00Z",
            "data": {"job_type": "email.send", "type": "notification.push"},
        })
        assert event.job_type == "email.send"


class TestEventType:
    def test_job_event_constants(self) -> None:
        assert EventType.JOB_ENQUEUED == "job.enqueued"
        assert EventType.JOB_STARTED == "job.started"
        assert EventType.JOB_COMPLETED == "job.completed"
        assert EventType.JOB_FAILED == "job.failed"
        assert EventType.JOB_RETRYING == "job.retrying"
        assert EventType.JOB_CANCELLED == "job.cancelled"
        assert EventType.JOB_DISCARDED == "job.discarded"
        assert EventType.JOB_HEARTBEAT == "job.heartbeat"
        assert EventType.JOB_SCHEDULED == "job.scheduled"

    def test_workflow_event_constants(self) -> None:
        assert EventType.WORKFLOW_STARTED == "workflow.started"
        assert EventType.WORKFLOW_COMPLETED == "workflow.completed"
        assert EventType.WORKFLOW_FAILED == "workflow.failed"

    def test_cron_event_constants(self) -> None:
        assert EventType.CRON_TRIGGERED == "cron.triggered"
        assert EventType.CRON_SKIPPED == "cron.skipped"

    def test_worker_event_constants(self) -> None:
        assert EventType.WORKER_STARTED == "worker.started"
        assert EventType.WORKER_STOPPED == "worker.stopped"
        assert EventType.WORKER_QUIET == "worker.quiet"


class TestQueue:
    def test_from_dict_minimal(self) -> None:
        q = Queue.from_dict({"name": "default"})
        assert q.name == "default"
        assert q.status == "active"
        assert q.created_at is None

    def test_from_dict_with_all_fields(self) -> None:
        q = Queue.from_dict({
            "name": "email",
            "status": "paused",
            "created_at": "2025-02-12T08:00:00Z",
        })
        assert q.name == "email"
        assert q.status == "paused"
        assert q.created_at == datetime(2025, 2, 12, 8, 0, tzinfo=UTC)

    def test_from_dict_null_created_at(self) -> None:
        q = Queue.from_dict({"name": "test", "created_at": None})
        assert q.created_at is None


class TestQueueStats:
    def test_from_dict_with_stats(self) -> None:
        stats = QueueStats.from_dict({
            "queue": "default",
            "status": "active",
            "stats": {
                "available": 100,
                "active": 5,
                "scheduled": 20,
                "retryable": 2,
                "discarded": 1,
                "completed_last_hour": 500,
                "failed_last_hour": 10,
                "avg_duration_ms": 150.5,
                "avg_wait_ms": 45.2,
                "throughput_per_second": 8.3,
            },
            "computed_at": "2025-02-12T12:00:00Z",
        })
        assert stats.queue == "default"
        assert stats.status == "active"
        assert stats.available == 100
        assert stats.active == 5
        assert stats.scheduled == 20
        assert stats.retryable == 2
        assert stats.discarded == 1
        assert stats.completed_last_hour == 500
        assert stats.failed_last_hour == 10
        assert stats.avg_duration_ms == 150.5
        assert stats.avg_wait_ms == 45.2
        assert stats.throughput_per_second == 8.3
        assert stats.computed_at == datetime(2025, 2, 12, 12, 0, tzinfo=UTC)

    def test_from_dict_empty_stats(self) -> None:
        stats = QueueStats.from_dict({
            "queue": "email",
            "status": "paused",
        })
        assert stats.queue == "email"
        assert stats.available == 0
        assert stats.active == 0
        assert stats.avg_duration_ms == 0.0
        assert stats.computed_at is None

    def test_from_dict_partial_stats(self) -> None:
        stats = QueueStats.from_dict({
            "queue": "default",
            "status": "active",
            "stats": {"available": 42},
        })
        assert stats.available == 42
        assert stats.active == 0
        assert stats.scheduled == 0
