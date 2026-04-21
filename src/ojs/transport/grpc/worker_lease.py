"""Projection and aggregation for worker lease RPCs."""

from __future__ import annotations

from ojs.errors import OJSCapabilityError
from ojs.transport.grpc.protobuf_time import milliseconds_to_duration

_DEFAULT_FETCH_VISIBILITY_TIMEOUT_MS = 30_000
_STATE_PRIORITY = {"running": 0, "quiet": 1, "terminate": 2}


def fetch_request(
    queues: list[str],
    count: int,
    worker_id: str | None,
    visibility_timeout_ms: int,
) -> dict[str, object]:
    """Build a fetch request without silently dropping unsupported options."""
    if visibility_timeout_ms != _DEFAULT_FETCH_VISIBILITY_TIMEOUT_MS:
        raise OJSCapabilityError(
            "The canonical OJS v1 gRPC FetchRequest cannot carry a custom "
            "visibility timeout; use HTTP transport or the 30000ms default."
        )
    request: dict[str, object] = {"queues": list(queues), "count": count}
    if worker_id:
        request["worker_id"] = worker_id
    return request


def heartbeat_requests(
    worker_id: str,
    active_jobs: list[str] | None,
    visibility_timeout_ms: int | None,
) -> list[dict[str, object]]:
    """Create one canonical heartbeat per active lease."""
    ids = list(active_jobs or ())
    if not ids:
        ids = [worker_id]
    requests: list[dict[str, object]] = []
    for lease_id in ids:
        request: dict[str, object] = {
            "id": lease_id,
            "worker_id": worker_id,
            "current_state": "WORKER_STATE_RUNNING",
        }
        if visibility_timeout_ms is not None:
            request["extend_by"] = milliseconds_to_duration(visibility_timeout_ms)
        requests.append(request)
    return requests


def aggregate_heartbeat_states(responses: list[dict[str, object]]) -> str:
    """Return the strongest server-directed lifecycle state."""
    selected = "running"
    for response in responses:
        directed = str(response.get("directed_state", "WORKER_STATE_RUNNING"))
        state = directed.lower().removeprefix("worker_state_")
        if _STATE_PRIORITY.get(state, 0) > _STATE_PRIORITY[selected]:
            selected = state
    return selected


__all__ = [
    "aggregate_heartbeat_states",
    "fetch_request",
    "heartbeat_requests",
]
