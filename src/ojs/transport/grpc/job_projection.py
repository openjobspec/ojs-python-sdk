"""Projection of protobuf Job messages into the public SDK envelope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import Message

from ojs.job import Job
from ojs.transport.grpc.protobuf_time import (
    duration_to_milliseconds,
    protobuf_duration_to_iso,
)

_HANDLED_JOB_FIELDS = {
    "args",
    "attempt",
    "completed_at",
    "created_at",
    "enqueued_at",
    "errors",
    "expires_at",
    "id",
    "max_attempts",
    "meta",
    "priority",
    "queue",
    "result",
    "retry",
    "scheduled_at",
    "started_at",
    "state",
    "tags",
    "timeout_ms",
    "type",
    "unique",
}
_job_fields = {field.name for field in fields(Job)}
if _job_fields != _HANDLED_JOB_FIELDS:
    raise RuntimeError(
        "gRPC job projection is out of sync with Job fields: "
        f"{sorted(_job_fields ^ _HANDLED_JOB_FIELDS)}"
    )

_CONFLICT_ACTIONS = {
    "UNIQUE_CONFLICT_ACTION_IGNORE": "ignore",
    "UNIQUE_CONFLICT_ACTION_REJECT": "reject",
    "UNIQUE_CONFLICT_ACTION_REPLACE": "replace",
    "UNIQUE_CONFLICT_ACTION_REPLACE_EXCEPT_SCHEDULE": "replace_except_schedule",
    "UNIQUE_CONFLICT_ACTION_UNSPECIFIED": "reject",
}


def project_job(job: Mapping[str, Any] | Message | None) -> dict[str, Any]:
    """Return the HTTP-shaped job dictionary consumed by ``Job.from_dict``.

    Meaningful zero/false values (for example an explicit
    ``retry.max_attempts = 0`` or ``retry.backoff_coefficient = 0.0``) are
    preserved rather than silently replaced by a locally hardcoded default.
    Protobuf singular scalar fields without explicit presence tracking
    cannot distinguish "never set" from "explicitly set to the zero value"
    at the wire level, so once a value has been extracted from the message
    (see ``_mapping``, which uses ``always_print_fields_with_no_presence``)
    it is trusted verbatim. A key is only left out of the projected
    dictionary when the underlying source (protobuf message or plain
    mapping) genuinely does not contain it, in which case ``Job.from_dict``
    / ``RetryPolicy.from_dict`` apply their own canonical defaults.
    """
    if job is None:
        return {}
    source = _mapping(job)
    projected: dict[str, Any] = {
        "id": source.get("id", ""),
        "type": source.get("type", ""),
        "queue": source.get("queue") or "default",
        "args": list(source.get("args", [])),
        "meta": dict(source.get("meta", {})),
        "state": _job_state(source.get("state", "available")),
        "priority": source.get("priority", 0),
        "attempt": source.get("attempt", 0),
        "tags": list(source.get("tags", [])),
        "errors": list(source.get("errors", [])),
        "result": source.get("result"),
    }
    if "max_attempts" in source:
        projected["max_attempts"] = source["max_attempts"]
    timeout = source.get("timeout")
    if isinstance(timeout, str):
        projected["timeout_ms"] = duration_to_milliseconds(timeout)
    retry = source.get("retry_policy")
    if isinstance(retry, Mapping):
        projected["retry"] = _project_retry(retry)
    unique = source.get("unique_policy")
    if isinstance(unique, Mapping):
        projected["unique"] = _project_unique(unique)
    for timestamp in (
        "created_at",
        "enqueued_at",
        "started_at",
        "completed_at",
        "scheduled_at",
        "expires_at",
    ):
        projected[timestamp] = source.get(timestamp)
    return projected


def _mapping(job: Mapping[str, Any] | Message) -> Mapping[str, Any]:
    if isinstance(job, Message):
        # ``always_print_fields_with_no_presence`` forces MessageToDict to
        # include singular scalar/repeated fields even when they hold their
        # protobuf zero value (0, 0.0, False, "", []). Without it, an
        # explicit ``max_attempts = 0`` is indistinguishable from a field
        # that was never set, and the projection below would have no way to
        # tell the difference from the dict alone. Message-typed fields
        # (retry_policy, unique_policy, timestamps, ...) already track real
        # presence via HasField and are unaffected by this flag: they are
        # only included when actually set on the message.
        return json_format.MessageToDict(
            job,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        )
    return job


def _job_state(state: object) -> str:
    if isinstance(state, str):
        normalized = state.lower().removeprefix("job_state_")
        # JOB_STATE_UNSPECIFIED (protobuf enum zero value) means "no state
        # was specified", unlike a genuinely meaningful zero value (see
        # module docstring on `project_job`); it maps to the SDK default
        # rather than being passed through as an invalid job state.
        return "available" if normalized == "unspecified" else normalized
    if isinstance(state, int):
        return {
            1: "scheduled",
            2: "available",
            3: "pending",
            4: "active",
            5: "completed",
            6: "retryable",
            7: "cancelled",
            8: "discarded",
        }.get(state, "available")
    return "available"


def _project_retry(retry: Mapping[str, Any]) -> dict[str, Any]:
    """Project a protobuf ``RetryPolicy`` dict, preserving explicit values.

    Each field is only included when present in ``retry`` (see
    ``_mapping``/``project_job`` for how presence is captured for protobuf
    sources). A key left out of the result defers to
    ``RetryPolicy.from_dict``'s own canonical default rather than this
    module silently substituting one, so an explicit ``max_attempts = 0``
    or ``backoff_coefficient = 0.0`` is never coerced into a nonzero
    default.
    """
    projected: dict[str, Any] = {}
    for field_name in ("max_attempts", "backoff_coefficient", "jitter"):
        if field_name in retry:
            projected[field_name] = retry[field_name]
    for field_name in ("initial_interval", "max_interval"):
        value = retry.get(field_name)
        if isinstance(value, str):
            projected[field_name] = protobuf_duration_to_iso(value)
    non_retryable_errors = retry.get("non_retryable_errors")
    if isinstance(non_retryable_errors, list) and non_retryable_errors:
        projected["non_retryable_errors"] = list(non_retryable_errors)
    return projected


def _project_unique(unique: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "key": list(unique.get("key", [])),
        "states": [_job_state(state) for state in unique.get("states", [])],
        "on_conflict": _CONFLICT_ACTIONS.get(
            str(unique.get("on_conflict", "")),
            "reject",
        ),
    }
    period = unique.get("period")
    if isinstance(period, str):
        projected["period"] = protobuf_duration_to_iso(period)
    for field_name in ("args_keys", "meta_keys"):
        value = unique.get(field_name)
        # A repeated protobuf field cannot distinguish "explicitly set to
        # an empty list" from "never set" at the wire level (unlike the
        # scalar fields handled in `_project_retry`, an empty repeated
        # field carries no extra information). Only a genuinely non-empty
        # list is meaningful here, so an empty/absent value is left out of
        # the projection and `UniquePolicy.from_dict` applies its own
        # `None` default (distinct in meaning from an explicit `[]`).
        if isinstance(value, list) and value:
            projected[field_name] = list(value)
    return projected


__all__ = ["project_job"]
