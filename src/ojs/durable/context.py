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

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from ojs.durable.checkpoint_endpoint import checkpoint_path
from ojs.durable.replay_loader import (
    DurableReplayError,
    ReplayLogEntry,
    load_replay_log,
)
from ojs.transport.capabilities import CheckpointTransport

T = TypeVar("T")


class DurableContext:
    """Deterministic execution context for durable job handlers.

    Records non-deterministic operations on first execution and replays
    them from a checkpoint on retry, ensuring idempotent re-execution.
    """

    def __init__(
        self,
        transport: CheckpointTransport | None,
        job_id: str,
        attempt: int,
    ) -> None:
        self._transport = transport
        self._job_id = job_id
        self._attempt = attempt
        self._entries: list[ReplayLogEntry] = []
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
            entries = await load_replay_log(transport, job_id)
            if entries:
                dc._entries = entries
                dc._replaying = True

        return dc

    def now(self) -> datetime:
        """Return the current time deterministically.

        On first execution, records ``datetime.now(UTC)``.
        On replay, returns the recorded value.
        """
        entry = self._replay_entry("time", "now")
        if entry is not None:
            if not isinstance(entry.result, str):
                raise DurableReplayError("replayed time value must be a string")
            return datetime.fromisoformat(entry.result)

        t = datetime.now(UTC)
        self._entries.append(
            ReplayLogEntry(
                seq=len(self._entries),
                type="time",
                result=t.isoformat(),
                key="now",
            )
        )
        self._replaying = False
        return t

    def random(self, num_bytes: int) -> str:
        """Return a deterministic random hex string.

        Args:
            num_bytes: Number of random bytes (output is 2x this in hex chars).
        """
        entry = self._replay_entry("random")
        if entry is not None:
            if not isinstance(entry.result, str):
                raise DurableReplayError("replayed random value must be a string")
            return entry.result

        s = secrets.token_hex(num_bytes)
        self._entries.append(ReplayLogEntry(seq=len(self._entries), type="random", result=s))
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
        entry = self._replay_entry("call", key)
        if entry is not None:
            return cast(T, entry.result)

        self._replaying = False
        result = await fn()
        self._entries.append(
            ReplayLogEntry(
                seq=len(self._entries),
                type="call",
                result=result,
                key=key,
            )
        )
        return result

    async def checkpoint(self, step_index: int, state: Any) -> None:
        """Save current execution state to the server.

        Call this after completing an important step to enable resume.

        Args:
            step_index: The step number (for ordering).
            state: Arbitrary state to save (must be JSON-serializable).
        """
        import json

        replay_log = json.dumps([entry.to_dict() for entry in self._entries])

        if self._transport is not None:
            await self._transport.request(
                method="POST",
                path=checkpoint_path(self._job_id),
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
                path=checkpoint_path(self._job_id),
            )

    @property
    def is_replaying(self) -> bool:
        """True if the context is currently replaying from a checkpoint."""
        return self._replaying and self._cursor < len(self._entries)

    def _check_replay_done(self) -> None:
        if self._cursor >= len(self._entries):
            self._replaying = False

    def _replay_entry(
        self,
        effect_type: str,
        key: str = "",
    ) -> ReplayLogEntry | None:
        if not self._replaying:
            return None
        if self._cursor >= len(self._entries):
            self._replaying = False
            return None
        entry = self._entries[self._cursor]
        if entry.type != effect_type:
            raise DurableReplayError(
                f"replay cursor {self._cursor} expected {effect_type!r}, found {entry.type!r}"
            )
        if effect_type == "call" and entry.key != key:
            raise DurableReplayError(
                f"replay cursor {self._cursor} expected side effect key {key!r}, "
                f"found {entry.key!r}"
            )
        self._cursor += 1
        self._check_replay_done()
        return entry
