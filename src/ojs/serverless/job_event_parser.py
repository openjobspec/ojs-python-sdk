"""Decode and validate OJS job events at serverless boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ojs.job import Job, JobState


class ServerlessEventError(ValueError):
    """A serverless invocation did not contain a valid OJS job envelope."""


def decode_event(value: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ServerlessEventError("event body is not valid UTF-8") from exc
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ServerlessEventError("event body is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise ServerlessEventError("event body must be a JSON object")
    return dict(value)


def parse_job_event(value: Mapping[str, Any]) -> Job:
    data = dict(value)
    job_id = data.get("id")
    job_type = data.get("type")
    args = data.get("args", [])
    meta = data.get("meta", {})
    state = data.get("state", JobState.ACTIVE.value)

    if not isinstance(job_id, str) or not job_id:
        raise ServerlessEventError("job id must be a non-empty string")
    if not isinstance(job_type, str) or not job_type:
        raise ServerlessEventError("job type must be a non-empty string")
    if not isinstance(args, list):
        raise ServerlessEventError("job args must be an array")
    if not isinstance(meta, Mapping):
        raise ServerlessEventError("job meta must be an object")
    try:
        normalized_state = JobState(state)
    except (TypeError, ValueError) as exc:
        raise ServerlessEventError(f"invalid job state: {state!r}") from exc

    normalized = {
        **data,
        "id": job_id,
        "type": job_type,
        "state": normalized_state.value,
        "args": list(args),
        "meta": dict(meta),
        "attempt": _integer_field(data, "attempt", 1, minimum=0),
        "max_attempts": _integer_field(data, "max_attempts", 3, minimum=1),
        "priority": _integer_field(data, "priority", 0),
    }
    return Job.from_dict(normalized)


def extract_job_event(value: Mapping[str, Any]) -> Job:
    envelope = dict(value)
    job_value = envelope.get("job", envelope)
    if not isinstance(job_value, Mapping):
        raise ServerlessEventError("job envelope field must be an object")
    return parse_job_event(job_value)


def _integer_field(
    data: Mapping[str, Any],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ServerlessEventError(f"job {name} must be an integer")
    if minimum is not None and value < minimum:
        raise ServerlessEventError(f"job {name} must be at least {minimum}")
    return value


__all__ = [
    "ServerlessEventError",
    "decode_event",
    "extract_job_event",
    "parse_job_event",
]
