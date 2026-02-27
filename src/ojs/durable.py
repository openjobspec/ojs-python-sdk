"""Durable execution support for the OJS Python SDK.

Provides deterministic wrappers around non-deterministic operations
(time, randomness, external calls). On first execution, operations are
recorded. On retry after a crash, recorded values are replayed from the
checkpoint instead of re-executing.

Usage::

    from ojs import Worker
    from ojs.durable import DurableContext

    worker = Worker("http://localhost:8080")

    @worker.register("etl.process")
    async def handle_etl(ctx):
        dc = await DurableContext.create(ctx)

        # Side effects are recorded for replay
        data = await dc.side_effect("fetch-data", fetch_from_api)
        await dc.checkpoint(1, {"fetched": True})

        # Deterministic time/random
        now = dc.now()
        rid = dc.random(16)

        await dc.complete()
        return {"records": len(data)}
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

BASE_PATH = "/ojs/v1"


class _SideEffectEntry:
    """A recorded side effect."""

    __slots__ = ("seq", "type", "key", "result")

    def __init__(self, seq: int, effect_type: str, result: Any, key: str = "") -> None:
        self.seq = seq
        self.type = effect_type
        self.key = key
        self.result = result

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"seq": self.seq, "type": self.type, "result": self.result}
        if self.key:
            d["key"] = self.key
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _SideEffectEntry:
        return cls(
            seq=data["seq"],
            effect_type=data["type"],
            result=data["result"],
            key=data.get("key", ""),
        )


class DurableContext:
    """Deterministic execution context for durable job handlers.

    Records non-deterministic operations on first execution and replays
    them from a checkpoint on retry, ensuring idempotent re-execution.
    """

    def __init__(self, transport: Any, job_id: str, attempt: int) -> None:
        self._transport = transport
        self._job_id = job_id
        self._attempt = attempt
        self._entries: list[_SideEffectEntry] = []
        self._cursor = 0
        self._replaying = False

    @classmethod
    async def create(cls, ctx: Any) -> DurableContext:
        """Create a DurableContext from a JobContext, loading any checkpoint.

        Args:
            ctx: The JobContext (must have .job.id, .job.attempt, and ._transport).
        """
        transport = getattr(ctx, "_transport", None) or getattr(ctx, "transport", None)
        job_id = ctx.job.id
        attempt = getattr(ctx.job, "attempt", 1)

        dc = cls(transport, job_id, attempt)

        if transport is not None:
            try:
                resp = await transport.request(
                    method="GET",
                    path=f"{BASE_PATH}/checkpoints/{job_id}/resume",
                )
                data = resp if isinstance(resp, dict) else getattr(resp, "body", {})
                if isinstance(data, dict) and data.get("has_checkpoint"):
                    cp = data.get("checkpoint", {})
                    metadata = cp.get("metadata", {}) if isinstance(cp, dict) else {}
                    replay_log = metadata.get("_replay_log", "")
                    if replay_log:
                        entries = json.loads(replay_log)
                        if isinstance(entries, list) and entries:
                            dc._entries = [_SideEffectEntry.from_dict(e) for e in entries]
                            dc._replaying = True
            except Exception:
                pass  # No checkpoint — start in record mode

        return dc

    def now(self) -> datetime:
        """Return the current time deterministically.

        On first execution, records ``datetime.now(UTC)``.
        On replay, returns the recorded value.
        """
        if self._replaying and self._cursor < len(self._entries):
            entry = self._entries[self._cursor]
            if entry.type == "time":
                self._cursor += 1
                self._check_replay_done()
                return datetime.fromisoformat(entry.result)

        t = datetime.now(timezone.utc)
        self._entries.append(_SideEffectEntry(
            seq=len(self._entries), effect_type="time", result=t.isoformat(), key="now",
        ))
        self._replaying = False
        return t

    def random(self, num_bytes: int) -> str:
        """Return a deterministic random hex string.

        Args:
            num_bytes: Number of random bytes (output is 2x this in hex chars).
        """
        if self._replaying and self._cursor < len(self._entries):
            entry = self._entries[self._cursor]
            if entry.type == "random":
                self._cursor += 1
                self._check_replay_done()
                return entry.result

        s = secrets.token_hex(num_bytes)
        self._entries.append(_SideEffectEntry(
            seq=len(self._entries), effect_type="random", result=s,
        ))
        self._replaying = False
        return s

    async def side_effect(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Execute a function deterministically.

        On first execution, ``fn`` is called and the result recorded.
        On replay, the recorded result is returned without calling ``fn``.

        Args:
            key: A unique key identifying this side effect.
            fn: An async function returning a JSON-serializable value.

        Returns:
            The result of ``fn`` (or the replayed result).

        Example::

            price = await dc.side_effect("fetch-price", lambda: fetch_price(product_id))
        """
        if self._replaying and self._cursor < len(self._entries):
            entry = self._entries[self._cursor]
            if entry.type == "call" and (not key or entry.key == key):
                self._cursor += 1
                self._check_replay_done()
                return entry.result  # type: ignore[return-value]

        self._replaying = False
        result = await fn()
        self._entries.append(_SideEffectEntry(
            seq=len(self._entries), effect_type="call", result=result, key=key,
        ))
        return result

    async def checkpoint(self, step_index: int, state: Any) -> None:
        """Save current execution state to the server.

        Call this after completing an important step to enable resume.

        Args:
            step_index: The step number (for ordering).
            state: Arbitrary state to save (must be JSON-serializable).
        """
        replay_log = json.dumps([e.to_dict() for e in self._entries])

        if self._transport is not None:
            await self._transport.request(
                method="POST",
                path=f"{BASE_PATH}/checkpoints/{self._job_id}",
                body={
                    "state": state,
                    "step_index": step_index,
                    "metadata": {
                        "_replay_log": replay_log,
                        "attempt": str(self._attempt),
                    },
                },
            )

    async def complete(self) -> None:
        """Clear the checkpoint after successful job completion."""
        if self._transport is not None:
            await self._transport.request(
                method="DELETE",
                path=f"{BASE_PATH}/checkpoints/{self._job_id}",
            )

    @property
    def is_replaying(self) -> bool:
        """True if the context is currently replaying from a checkpoint."""
        return self._replaying and self._cursor < len(self._entries)

    def _check_replay_done(self) -> None:
        if self._cursor >= len(self._entries):
            self._replaying = False
