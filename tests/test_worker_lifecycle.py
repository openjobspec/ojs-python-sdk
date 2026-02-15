"""Tests for Worker lifecycle, fetch loop, heartbeat, and shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

import ojs
from ojs.job import Job, JobState
from ojs.worker import WorkerState
from tests.conftest import FakeTransport


def _make_job(job_id: str = "job-1", job_type: str = "test.echo") -> Job:
    return Job(id=job_id, type=job_type, state=JobState.ACTIVE, args=["hello"])


async def _await_worker(task: asyncio.Task[None], timeout: float = 5.0) -> None:
    """Await a worker task, suppressing the expected CancelledError exit."""
    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
        await asyncio.wait_for(task, timeout=timeout)


async def _run_worker_briefly(
    worker: ojs.Worker,
    *,
    pre_stop_delay: float = 0.05,
    timeout: float = 5.0,
) -> None:
    """Start worker, wait briefly, stop, and await completion."""
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(pre_stop_delay)
    await worker.stop()
    await _await_worker(task, timeout=timeout)


class TestWorkerLifecycle:
    """Test start/stop and state transitions."""

    async def test_start_and_stop(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=0.01,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)
        assert worker.state == WorkerState.RUNNING

        await worker.stop()
        await _await_worker(task)
        assert worker.state == WorkerState.IDLE

    async def test_start_processes_job_then_stop(self) -> None:
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job()])

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> dict[str, bool]:
            return {"done": True}

        await _run_worker_briefly(worker, pre_stop_delay=0.1)

        assert len(transport.acked) == 1
        assert transport.acked[0]["job_id"] == "job-1"
        assert transport.acked[0]["result"] == {"done": True}

    async def test_start_with_no_handlers_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        transport = FakeTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        with caplog.at_level(logging.WARNING):
            await _run_worker_briefly(worker)

        assert any("no registered handlers" in r.message for r in caplog.records)


class TestFetchLoop:
    """Test the fetch loop behavior."""

    async def test_fetch_multiple_jobs_sequentially(self) -> None:
        transport = FakeTransport()
        transport.set_fetch_jobs(
            [
                _make_job("job-1"),
                _make_job("job-2"),
            ]
        )

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        await _run_worker_briefly(worker, pre_stop_delay=0.2)

        assert len(transport.acked) == 2
        acked_ids = {a["job_id"] for a in transport.acked}
        assert acked_ids == {"job-1", "job-2"}

    async def test_fetch_error_recovers(self) -> None:
        """Transport error in fetch should not crash the worker."""
        transport = FakeTransport()
        transport.set_fetch_error(ConnectionError("network down"))

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.1)

        # Worker should still be running after the error
        assert worker.state == WorkerState.RUNNING

        # Now give it a real job to process
        transport.set_fetch_jobs([_make_job()])
        await asyncio.sleep(0.15)

        await worker.stop()
        await _await_worker(task)

        assert len(transport.acked) == 1

    async def test_semaphore_limits_concurrency(self) -> None:
        """Semaphore should limit concurrent job processing."""
        transport = FakeTransport()
        active_count = 0
        max_active = 0

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            concurrency=2,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.slow")
        async def handler(ctx: ojs.JobContext) -> str:
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1
            return "ok"

        transport.set_fetch_jobs([_make_job(f"job-{i}", "test.slow") for i in range(4)])

        await _run_worker_briefly(worker, pre_stop_delay=0.5)

        assert len(transport.acked) == 4
        assert max_active <= 2

    async def test_semaphore_released_on_fetch_error(self) -> None:
        """Semaphore must be released when fetch raises."""
        transport = FakeTransport()
        transport.set_fetch_error(RuntimeError("transient"))

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            concurrency=1,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.1)

        # After error, semaphore should be released so new fetches work
        transport.set_fetch_jobs([_make_job()])
        await asyncio.sleep(0.15)

        await worker.stop()
        await _await_worker(task)

        assert len(transport.acked) == 1


class TestHeartbeat:
    """Test heartbeat loop and server-initiated state changes."""

    async def test_heartbeat_quiet_stops_fetching(self) -> None:
        """Server returning quiet should stop new job fetching."""
        transport = FakeTransport()
        transport.set_heartbeat_responses(
            [
                {"state": "quiet"},
            ]
        )

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=0.01,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.1)
        assert worker.state == WorkerState.QUIET

        await worker.stop()
        await _await_worker(task)

    async def test_heartbeat_terminate_triggers_shutdown(self) -> None:
        """Server returning terminate should trigger graceful shutdown."""
        transport = FakeTransport()
        transport.set_heartbeat_responses(
            [
                {"state": "terminate"},
            ]
        )

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=0.01,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await _await_worker(task)
        assert worker.state == WorkerState.IDLE


class TestGracefulShutdown:
    """Test graceful shutdown with active jobs."""

    async def test_active_jobs_complete_during_grace_period(self) -> None:
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job()])

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            await asyncio.sleep(0.15)
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)
        await worker.stop()
        await _await_worker(task, timeout=30.0)

        assert len(transport.acked) == 1

    async def test_worker_state_returns_to_idle_after_stop(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=0.01,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        assert worker.state == WorkerState.IDLE
        await _run_worker_briefly(worker)
        assert worker.state == WorkerState.IDLE


class TestWorkerProperties:
    """Test worker property accessors."""

    def test_worker_id_is_unique(self) -> None:
        t = FakeTransport()
        w1 = ojs.Worker("http://localhost:8080", transport=t)
        w2 = ojs.Worker("http://localhost:8080", transport=t)
        assert w1.worker_id != w2.worker_id

    def test_initial_state_is_idle(self) -> None:
        t = FakeTransport()
        w = ojs.Worker("http://localhost:8080", transport=t)
        assert w.state == WorkerState.IDLE

    def test_default_queues(self) -> None:
        t = FakeTransport()
        w = ojs.Worker("http://localhost:8080", transport=t)
        assert w._queues == ["default"]

    def test_custom_queues(self) -> None:
        t = FakeTransport()
        w = ojs.Worker("http://localhost:8080", transport=t, queues=["email", "reports"])
        assert w._queues == ["email", "reports"]
