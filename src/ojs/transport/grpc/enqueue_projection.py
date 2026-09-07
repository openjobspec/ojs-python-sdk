"""Field-complete projection of OJS enqueue envelopes to protobuf JSON."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime
from typing import Any

from ojs.errors import OJSCapabilityError, OJSValidationError
from ojs.job import JobRequest
from ojs.transport.grpc.protobuf_time import (
    expiry_to_ttl,
    iso_duration_to_protobuf,
    milliseconds_to_duration,
)

_HANDLED_REQUEST_FIELDS = {
    "args",
    "delay_until",
    "expires_at",
    "meta",
    "priority",
    "queue",
    "retry",
    "schema",
    "tags",
    "timeout_ms",
    "type",
    "unique",
}
_request_fields = {field.name for field in fields(JobRequest)}
if _request_fields != _HANDLED_REQUEST_FIELDS:
    raise RuntimeError(
        "gRPC enqueue projection is out of sync with JobRequest fields: "
        f"{sorted(_request_fields ^ _HANDLED_REQUEST_FIELDS)}"
    )

_CONFLICT_ACTIONS = {
    "ignore": "UNIQUE_CONFLICT_ACTION_IGNORE",
    "reject": "UNIQUE_CONFLICT_ACTION_REJECT",
    "replace": "UNIQUE_CONFLICT_ACTION_REPLACE",
    "replace_except_schedule": "UNIQUE_CONFLICT_ACTION_REPLACE_EXCEPT_SCHEDULE",
}


def project_enqueue(
    body: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Project an HTTP-shaped enqueue body into the canonical gRPC message."""
    job_type = body.get("type")
    args = body.get("args", [])
    if not isinstance(job_type, str) or not job_type:
        raise OJSValidationError("enqueue type must be a non-empty string")
    if not isinstance(args, list):
        raise OJSValidationError("enqueue args must be a list")
    if body.get("schema") is not None:
        raise OJSCapabilityError(
            "The canonical OJS v1 gRPC EnqueueRequest has no schema field. "
            "Use HTTP transport for schema-validated enqueue operations."
        )

    source_options = body.get("options")
    if source_options is None:
        source_options = {}
    if not isinstance(source_options, Mapping):
        raise OJSValidationError("enqueue options must be an object")
    options = _project_options(body, source_options, now=now)

    request: dict[str, Any] = {"type": job_type, "args": list(args)}
    if options:
        request["options"] = options
    return request


def _project_options(
    body: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    now: datetime | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    queue = source.get("queue", body.get("queue"))
    if isinstance(queue, str) and queue:
        options["queue"] = queue
    priority = source.get("priority", body.get("priority"))
    if isinstance(priority, int):
        options["priority"] = priority
    delay_until = source.get("delay_until")
    if isinstance(delay_until, str):
        options["delay_until"] = delay_until
    timeout_ms = source.get("timeout_ms")
    if isinstance(timeout_ms, int):
        options["timeout"] = milliseconds_to_duration(timeout_ms)
    expires_at = source.get("expires_at")
    if isinstance(expires_at, str):
        options["ttl"] = expiry_to_ttl(expires_at, now=now)

    retry = source.get("retry")
    if isinstance(retry, Mapping):
        options["retry"] = _project_retry(retry)
        max_attempts = retry.get("max_attempts")
        if isinstance(max_attempts, int):
            options["max_attempts"] = max_attempts
    unique = source.get("unique")
    if isinstance(unique, Mapping):
        options["unique"] = _project_unique(unique)

    tags = source.get("tags", body.get("tags"))
    if isinstance(tags, list):
        options["tags"] = list(tags)
    meta = body.get("meta")
    if isinstance(meta, Mapping):
        options["meta"] = dict(meta)
        trace_id = meta.get("trace_id")
        if isinstance(trace_id, str):
            options["trace_id"] = trace_id
    visibility_timeout_ms = source.get("visibility_timeout_ms")
    if isinstance(visibility_timeout_ms, int):
        options["visibility_timeout"] = milliseconds_to_duration(visibility_timeout_ms)
    return options


def _project_retry(retry: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    max_attempts = retry.get("max_attempts")
    if isinstance(max_attempts, int):
        projected["max_attempts"] = max_attempts
    for source, target in (
        ("initial_interval", "initial_interval"),
        ("max_interval", "max_interval"),
    ):
        value = retry.get(source)
        if isinstance(value, str):
            projected[target] = iso_duration_to_protobuf(value)
    coefficient = retry.get("backoff_coefficient")
    if isinstance(coefficient, (int, float)):
        projected["backoff_coefficient"] = coefficient
    jitter = retry.get("jitter")
    if isinstance(jitter, bool):
        projected["jitter"] = jitter
    errors = retry.get("non_retryable_errors")
    if isinstance(errors, list):
        projected["non_retryable_errors"] = list(errors)
    exhaustion = retry.get("on_exhaustion")
    if isinstance(exhaustion, str):
        projected["on_exhaustion"] = exhaustion
    return projected


def _project_unique(unique: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    keys = unique.get("key")
    if isinstance(keys, list):
        projected["key"] = list(keys)
    period = unique.get("period")
    if isinstance(period, str):
        projected["period"] = iso_duration_to_protobuf(period)
    conflict = unique.get("on_conflict")
    if isinstance(conflict, str):
        try:
            projected["on_conflict"] = _CONFLICT_ACTIONS[conflict]
        except KeyError:
            raise OJSValidationError(
                f"unsupported unique on_conflict value: {conflict!r}"
            ) from None
    states = unique.get("states")
    if isinstance(states, list):
        projected["states"] = [f"JOB_STATE_{str(state).upper()}" for state in states]
    for field_name in ("args_keys", "meta_keys"):
        value = unique.get(field_name)
        if isinstance(value, list):
            projected[field_name] = list(value)
    return projected


__all__ = ["project_enqueue"]
