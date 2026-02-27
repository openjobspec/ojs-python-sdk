"""Tests for the durable execution module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ojs.durable import DurableContext, _SideEffectEntry


class FakeTransport:
    """Mock transport for testing."""

    def __init__(self, resume_response=None):
        self._resume = resume_response or {"has_checkpoint": False}
        self.requests: list[dict] = []

    async def request(self, *, method: str, path: str, body=None, **kwargs):
        self.requests.append({"method": method, "path": path, "body": body})
        if "/resume" in path:
            return self._resume
        return {}


class FakeJob:
    def __init__(self, job_id="job-1", attempt=1):
        self.id = job_id
        self.attempt = attempt


class FakeJobContext:
    def __init__(self, job_id="job-1", attempt=1, transport=None):
        self.job = FakeJob(job_id, attempt)
        self._transport = transport or FakeTransport()
        self.transport = self._transport


@pytest.mark.asyncio
async def test_create_record_mode():
    ctx = FakeJobContext()
    dc = await DurableContext.create(ctx)
    assert not dc.is_replaying


@pytest.mark.asyncio
async def test_now():
    ctx = FakeJobContext()
    dc = await DurableContext.create(ctx)
    t = dc.now()
    assert isinstance(t, datetime)
    assert t.tzinfo is not None


@pytest.mark.asyncio
async def test_random():
    ctx = FakeJobContext()
    dc = await DurableContext.create(ctx)
    r = dc.random(16)
    assert len(r) == 32  # 16 bytes = 32 hex chars
    assert all(c in "0123456789abcdef" for c in r)


@pytest.mark.asyncio
async def test_side_effect():
    ctx = FakeJobContext()
    dc = await DurableContext.create(ctx)

    call_count = 0

    async def compute():
        nonlocal call_count
        call_count += 1
        return {"value": 42}

    result = await dc.side_effect("compute", compute)
    assert result == {"value": 42}
    assert call_count == 1


@pytest.mark.asyncio
async def test_replay_from_checkpoint():
    replay_log = json.dumps([
        {"seq": 0, "type": "time", "key": "now", "result": "2026-01-15T10:00:00+00:00"},
        {"seq": 1, "type": "random", "result": "deadbeef01234567"},
        {"seq": 2, "type": "call", "key": "api-call", "result": {"price": 99.99}},
    ])

    transport = FakeTransport(resume_response={
        "has_checkpoint": True,
        "checkpoint": {
            "metadata": {"_replay_log": replay_log},
        },
    })

    ctx = FakeJobContext(job_id="job-replay", attempt=2, transport=transport)
    dc = await DurableContext.create(ctx)
    assert dc.is_replaying

    # Replay time
    t = dc.now()
    assert t.year == 2026
    assert t.month == 1

    # Replay random
    r = dc.random(8)
    assert r == "deadbeef01234567"

    # Replay side effect — should NOT call fn
    async def should_not_call():
        raise AssertionError("should not be called during replay")

    result = await dc.side_effect("api-call", should_not_call)
    assert result == {"price": 99.99}

    # After exhausting replay
    assert not dc.is_replaying


@pytest.mark.asyncio
async def test_checkpoint():
    transport = FakeTransport()
    ctx = FakeJobContext(transport=transport)
    dc = await DurableContext.create(ctx)

    dc.now()
    dc.random(8)

    await dc.checkpoint(2, {"step": "transform"})

    # Verify POST was sent
    post_reqs = [r for r in transport.requests if r["method"] == "POST"]
    assert len(post_reqs) == 1
    assert post_reqs[0]["body"]["step_index"] == 2


@pytest.mark.asyncio
async def test_complete():
    transport = FakeTransport()
    ctx = FakeJobContext(transport=transport)
    dc = await DurableContext.create(ctx)

    await dc.complete()

    delete_reqs = [r for r in transport.requests if r["method"] == "DELETE"]
    assert len(delete_reqs) == 1


@pytest.mark.asyncio
async def test_no_transport():
    """Should work without a transport (record-only mode)."""
    ctx = FakeJobContext()
    ctx._transport = None
    ctx.transport = None

    dc = await DurableContext.create(ctx)
    assert not dc.is_replaying

    t = dc.now()
    assert isinstance(t, datetime)

    r = dc.random(8)
    assert len(r) == 16


def test_side_effect_entry_roundtrip():
    entry = _SideEffectEntry(seq=0, effect_type="call", result={"x": 1}, key="test")
    d = entry.to_dict()
    restored = _SideEffectEntry.from_dict(d)
    assert restored.seq == 0
    assert restored.type == "call"
    assert restored.key == "test"
    assert restored.result == {"x": 1}
