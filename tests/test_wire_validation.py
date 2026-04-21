"""Malformed wire payload characterization tests."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from ojs._utils import parse_datetime
from ojs.errors import OJSValidationError
from ojs.events import Event
from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.workflow import Workflow


def test_parse_datetime_replaces_only_terminal_z() -> None:
    class RecordingDatetime:
        value = ""

        @classmethod
        def fromisoformat(cls, value: str) -> datetime:
            cls.value = value
            return datetime(2025, 1, 1, tzinfo=UTC)

    with patch("ojs._utils.datetime", RecordingDatetime):
        parse_datetime("embedded-Z-value")
        assert RecordingDatetime.value == "embedded-Z-value"

        parse_datetime("terminal-Z")
        assert RecordingDatetime.value == "terminal-+00:00"


def test_parse_datetime_wraps_malformed_values() -> None:
    with pytest.raises(OJSValidationError, match=r"payload\.created_at"):
        parse_datetime("not-a-timestamp", path="payload.created_at")


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({"type": "email.send"}, "job.id"),
        ({"id": "j1", "type": 42}, "job.type"),
        ({"id": "j1", "type": "email.send", "state": "mystery"}, "job.state"),
        ({"id": "j1", "type": "email.send", "args": {}}, "job.args"),
        (
            {"id": "j1", "type": "email.send", "created_at": "not-a-date"},
            "job.created_at",
        ),
        ({"id": "j1", "type": "email.send", "errors": ["broken"]}, "job.errors[0]"),
    ],
)
def test_job_rejects_malformed_wire_fields(
    payload: dict[str, object],
    path: str,
) -> None:
    with pytest.raises(OJSValidationError, match=re.escape(path)):
        Job.from_dict(payload)


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({"name": "batch", "state": "running"}, "workflow.id"),
        (
            {
                "id": "wf1",
                "name": "batch",
                "state": "running",
                "steps": [{"id": "s1", "type": 7}],
            },
            "workflow.steps[0].type",
        ),
        (
            {"id": "wf1", "name": "batch", "state": "running", "steps": {}},
            "workflow.steps",
        ),
        (
            {
                "id": "wf1",
                "name": "batch",
                "state": "running",
                "callbacks": {"success": "not-an-object"},
            },
            "workflow.callbacks.success",
        ),
    ],
)
def test_workflow_rejects_malformed_wire_fields(
    payload: dict[str, object],
    path: str,
) -> None:
    with pytest.raises(OJSValidationError) as raised:
        Workflow.from_dict(payload)
    assert path in str(raised.value)


@pytest.mark.parametrize(
    ("factory", "payload", "path"),
    [
        (Queue.from_dict, {}, "queue.name"),
        (
            QueueStats.from_dict,
            {"queue": "default", "stats": []},
            "queue_stats.stats",
        ),
        (
            QueueStats.from_dict,
            {"queue": "default", "stats": {"available": "many"}},
            "queue_stats.stats.available",
        ),
        (
            Event.from_dict,
            {"event": "job.completed", "timestamp": "not-a-date"},
            "event.timestamp",
        ),
        (
            Event.from_dict,
            {"event": "job.completed", "timestamp": "2025-01-01T00:00:00Z", "data": []},
            "event.data",
        ),
    ],
)
def test_other_models_report_the_failing_wire_path(
    factory: Callable[[dict[str, Any]], object],
    payload: dict[str, Any],
    path: str,
) -> None:
    with pytest.raises(OJSValidationError) as raised:
        factory(payload)
    assert path in str(raised.value)
