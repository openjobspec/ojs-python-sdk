"""Fail-closed loading and validation of durable replay logs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ojs.durable.checkpoint_endpoint import resume_path
from ojs.errors import JobNotFoundError, OJSError
from ojs.transport.capabilities import CheckpointTransport


class DurableReplayError(OJSError):
    """A durable checkpoint cannot be replayed safely."""


@dataclass(frozen=True, slots=True)
class ReplayLogEntry:
    """One validated deterministic value in a replay log."""

    seq: int
    type: str
    result: Any
    key: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "seq": self.seq,
            "type": self.type,
            "result": self.result,
        }
        if self.key:
            result["key"] = self.key
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReplayLogEntry:
        seq = data.get("seq")
        effect_type = data.get("type")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise DurableReplayError("replay entry seq must be an integer")
        if effect_type not in {"time", "random", "call"}:
            raise DurableReplayError(f"replay entry {seq} has invalid type {effect_type!r}")
        if "result" not in data:
            raise DurableReplayError(f"replay entry {seq} is missing result")
        key = data.get("key", "")
        if not isinstance(key, str):
            raise DurableReplayError(f"replay entry {seq} key must be a string")
        return cls(seq=seq, type=effect_type, result=data["result"], key=key)


async def load_replay_log(
    transport: CheckpointTransport,
    job_id: str,
) -> list[ReplayLogEntry] | None:
    """Load a replay log, returning ``None`` only for a missing checkpoint."""
    try:
        response = await transport.request(
            method="GET",
            path=resume_path(job_id),
        )
    except JobNotFoundError:
        return None
    if not isinstance(response, Mapping):
        raise DurableReplayError("checkpoint response must be an object")
    if response.get("has_checkpoint") is False:
        return None
    if response.get("has_checkpoint") is not True:
        raise DurableReplayError("checkpoint response is missing has_checkpoint")

    checkpoint = response.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise DurableReplayError("checkpoint payload must be an object")
    metadata = checkpoint.get("metadata")
    if not isinstance(metadata, Mapping):
        raise DurableReplayError("checkpoint metadata must be an object")
    raw_log = metadata.get("_replay_log")
    if not isinstance(raw_log, str) or not raw_log:
        raise DurableReplayError("checkpoint replay log is missing")
    try:
        decoded = json.loads(raw_log)
    except json.JSONDecodeError as exc:
        raise DurableReplayError(f"checkpoint replay log is invalid JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise DurableReplayError("checkpoint replay log must be an array")

    entries: list[ReplayLogEntry] = []
    for expected_seq, raw_entry in enumerate(decoded):
        if not isinstance(raw_entry, Mapping):
            raise DurableReplayError(f"replay entry {expected_seq} must be an object")
        entry = ReplayLogEntry.from_dict(raw_entry)
        if entry.seq != expected_seq:
            raise DurableReplayError(
                f"replay sequence mismatch: expected {expected_seq}, got {entry.seq}"
            )
        entries.append(entry)
    return entries


__all__ = [
    "CheckpointTransport",
    "DurableReplayError",
    "ReplayLogEntry",
    "load_replay_log",
]
