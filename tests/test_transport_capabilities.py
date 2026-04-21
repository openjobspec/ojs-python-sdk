"""Tests for capability-specific transport protocols."""

from __future__ import annotations

from typing import Any

from ojs.job import Job
from ojs.transport import CheckpointTransport, ProducerTransport, ProgressTransport


class MinimalProducer:
    async def push(self, body: dict[str, Any]) -> Job:
        raise NotImplementedError

    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        return []

    async def info(self, job_id: str) -> Job:
        raise NotImplementedError

    async def cancel(self, job_id: str) -> Job:
        raise NotImplementedError


class MinimalCheckpointStore:
    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"method": method, "path": path, "body": body}


class MinimalProgressReporter:
    async def progress(self, body: dict[str, Any]) -> dict[str, Any]:
        return body


def accepts_producer(transport: ProducerTransport) -> ProducerTransport:
    return transport


def accepts_checkpoint(transport: CheckpointTransport) -> CheckpointTransport:
    return transport


def accepts_progress(transport: ProgressTransport) -> ProgressTransport:
    return transport


def test_minimal_transports_satisfy_narrow_capabilities() -> None:
    assert isinstance(accepts_producer(MinimalProducer()), ProducerTransport)
    assert isinstance(accepts_checkpoint(MinimalCheckpointStore()), CheckpointTransport)
    assert isinstance(accepts_progress(MinimalProgressReporter()), ProgressTransport)


def test_unrelated_capabilities_are_not_required() -> None:
    producer = MinimalProducer()

    assert not isinstance(producer, CheckpointTransport)
    assert not isinstance(producer, ProgressTransport)
