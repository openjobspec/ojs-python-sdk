"""Tests for Worker lifecycle, fetch loop, heartbeat, and shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time

import pytest

import ojs
from ojs.errors import OJSConnectionError
from ojs.job import Job, JobState
from ojs.worker import WorkerState
from ojs.worker.run_state import WorkerRunState
from tests.conftest import FakeTransport


def _make_job(job_id: str = "job-1", job_type: str = "test.echo") -> Job:
    return Job(id=job_id, type=job_type, state=JobState.ACTIVE, args=["hello"])


async def _await_worker(
    task: asyncio.Task[None],
    wait_timeout: float = 5.0,
) -> None:
    """Await a worker task, suppressing the expected CancelledError exit."""
    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
        await asyncio.wait_for(task, timeout=wait_timeout)


async def _run_worker_briefly(
    worker: ojs.Worker,
    *,
    pre_stop_delay: float = 0.05,
    wait_timeout: float = 5.0,
) -> None:
    """Start worker, wait briefly, stop, and await completion."""
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(pre_stop_delay)
    await worker.stop()
    await _await_worker(task, wait_timeout=wait_timeout)


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

    async def test_worker_can_start_stop_and_start_again(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return str(ctx.args[0])

        transport.set_fetch_jobs([_make_job("job-1")])
        await _run_worker_briefly(worker, pre_stop_delay=0.1)
        transport.set_fetch_jobs([_make_job("job-2")])
        await _run_worker_briefly(worker, pre_stop_delay=0.1)

        assert [entry["job_id"] for entry in transport.acked] == ["job-1", "job-2"]

    async def test_stop_interrupts_heartbeat_backoff(self) -> None:
        class FailingHeartbeatTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.heartbeat_started = asyncio.Event()

            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                self.heartbeat_started.set()
                raise OJSConnectionError("heartbeat unavailable")

        transport = FailingHeartbeatTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=60,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        task = asyncio.create_task(worker.start())
        await transport.heartbeat_started.wait()
        started = time.monotonic()
        await worker.stop()
        await _await_worker(task, wait_timeout=1)

        assert time.monotonic() - started < 0.5

    async def test_cancelling_start_cleans_up_owned_loop_tasks(self) -> None:
        class BlockingTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.fetch_started = asyncio.Event()
                self.heartbeat_started = asyncio.Event()
                self.fetch_cancelled = asyncio.Event()
                self.heartbeat_cancelled = asyncio.Event()

            async def fetch(
                self,
                queues: list[str],
                count: int = 1,
                worker_id: str | None = None,
                visibility_timeout_ms: int = 30000,
            ) -> list[Job]:
                self.fetch_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.fetch_cancelled.set()
                return []

            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                self.heartbeat_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.heartbeat_cancelled.set()
                return {}

        transport = BlockingTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            grace_period=0,
        )
        worker.handler("test.echo", lambda ctx: asyncio.sleep(0))

        worker_task = asyncio.create_task(worker.start())
        await asyncio.gather(
            transport.fetch_started.wait(),
            transport.heartbeat_started.wait(),
        )
        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task

        assert transport.fetch_cancelled.is_set()
        assert transport.heartbeat_cancelled.is_set()
        assert worker.state == WorkerState.IDLE


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

    async def test_fetch_count_never_exceeds_available_capacity(self) -> None:
        class CountingTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.requested_counts: list[int] = []

            async def fetch(
                self,
                queues: list[str],
                count: int = 1,
                worker_id: str | None = None,
                visibility_timeout_ms: int = 30000,
            ) -> list[Job]:
                self.requested_counts.append(count)
                return await super().fetch(
                    queues,
                    count,
                    worker_id,
                    visibility_timeout_ms,
                )

        transport = CountingTransport()
        transport.set_fetch_jobs([_make_job(f"job-{index}", "test.slow") for index in range(4)])
        release = asyncio.Event()
        two_started = asyncio.Event()
        started = 0
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            concurrency=2,
            poll_interval=0.01,
            heartbeat_interval=60,
            grace_period=0,
        )

        @worker.register("test.slow")
        async def handler(ctx: ojs.JobContext) -> str:
            nonlocal started
            started += 1
            if started == 2:
                two_started.set()
            await release.wait()
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.wait_for(two_started.wait(), timeout=1)
        await asyncio.sleep(0.05)
        assert transport.requested_counts == [2]

        release.set()
        await asyncio.sleep(0.1)
        await worker.stop()
        await _await_worker(task)

        assert all(count <= 2 for count in transport.requested_counts)

    async def test_surplus_backend_leases_are_explicitly_nacked(self) -> None:
        class OversizedTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.returned = False

            async def fetch(
                self,
                queues: list[str],
                count: int = 1,
                worker_id: str | None = None,
                visibility_timeout_ms: int = 30000,
            ) -> list[Job]:
                if self.returned:
                    return []
                self.returned = True
                return [_make_job(f"job-{index}") for index in range(3)]

        transport = OversizedTransport()
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

        await _run_worker_briefly(worker, pre_stop_delay=0.1)

        assert [entry["job_id"] for entry in transport.acked] == ["job-0"]
        assert [entry["job_id"] for entry in transport.nacked] == ["job-1", "job-2"]
        assert all(entry["error"]["code"] == "worker_over_capacity" for entry in transport.nacked)


class TestHeartbeat:
    """Test heartbeat loop and server-initiated state changes."""

    async def test_heartbeat_quiet_stops_fetching(self) -> None:
        """Server returning quiet should stop new job fetching."""
        transport = FakeTransport()
        transport.set_heartbeat_responses([{"state": "quiet"}] * 20)

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

    async def test_running_directive_resumes_quiet_worker(self) -> None:
        transport = FakeTransport()
        transport.set_heartbeat_responses(
            [
                {"state": "quiet", "jobs_extended": []},
                {"state": "running", "jobs_extended": []},
                {"state": "terminate", "jobs_extended": []},
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

        states: list[WorkerState] = []
        original_heartbeat = transport.heartbeat

        async def heartbeat(*args, **kwargs):
            response = await original_heartbeat(*args, **kwargs)
            states.append(worker.state)
            return response

        transport.heartbeat = heartbeat  # type: ignore[method-assign]
        await worker.start()

        assert states == [
            WorkerState.RUNNING,
            WorkerState.QUIET,
            WorkerState.RUNNING,
        ]

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

    async def test_only_server_confirmed_jobs_extend_local_leases(self) -> None:
        class SelectiveHeartbeatTransport(FakeTransport):
            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                return {
                    "state": "terminate",
                    "jobs_extended": ["job-a"],
                }

        class ExecutionSpy:
            def active_job_ids(self) -> list[str]:
                return ["job-a", "job-b"]

            def extend_leases(
                self,
                visibility_timeout_ms: int,
                *,
                job_ids: set[str] | None = None,
            ) -> None:
                self.extended = (visibility_timeout_ms, job_ids)

        class RunStateSpy:
            def __init__(self) -> None:
                self.shutdown = asyncio.Event()
                self.executions = ExecutionSpy()

            def request_shutdown(self) -> None:
                self.shutdown.set()

        run_state = RunStateSpy()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=SelectiveHeartbeatTransport(),
            install_signal_handlers=False,
        )

        await worker._heartbeat_loop(run_state)  # type: ignore[arg-type]

        assert run_state.executions.extended == (30_000, {"job-a"})

    async def test_missing_heartbeat_confirmation_extends_no_local_leases(self) -> None:
        class UnconfirmedHeartbeatTransport(FakeTransport):
            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                return {"state": "terminate"}

        class ExecutionSpy:
            def active_job_ids(self) -> list[str]:
                return ["job-a"]

            def extend_leases(
                self,
                visibility_timeout_ms: int,
                *,
                job_ids: set[str] | None = None,
            ) -> None:
                self.extended = job_ids

        class RunStateSpy:
            def __init__(self) -> None:
                self.shutdown = asyncio.Event()
                self.executions = ExecutionSpy()

            def request_shutdown(self) -> None:
                self.shutdown.set()

        run_state = RunStateSpy()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=UnconfirmedHeartbeatTransport(),
            install_signal_handlers=False,
        )

        await worker._heartbeat_loop(run_state)  # type: ignore[arg-type]

        assert run_state.executions.extended == set()


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
        await _await_worker(task, wait_timeout=30.0)

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

    async def test_cancelled_execution_remains_cancelled_after_nack(self) -> None:
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job()])
        entered = asyncio.Event()
        execution_tasks: list[asyncio.Task[object]] = []
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
            grace_period=0,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError("handler has no current task")
            execution_tasks.append(task)
            entered.set()
            await asyncio.Event().wait()
            return "unreachable"

        worker_task = asyncio.create_task(worker.start())
        await entered.wait()
        await worker.stop()
        await _await_worker(worker_task)

        assert execution_tasks[0].cancelled()
        assert transport.nacked[0]["error"]["code"] == "cancelled"


class TestExecutionRegistry:
    async def test_duplicate_job_ids_are_tracked_as_distinct_executions(self) -> None:
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job("same-id"), _make_job("same-id")])
        release = asyncio.Event()
        both_started = asyncio.Event()
        started = 0
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            concurrency=2,
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await release.wait()
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.wait_for(both_started.wait(), timeout=1)
        release.set()
        await asyncio.sleep(0.05)
        await worker.stop()
        await _await_worker(task)

        assert [entry["job_id"] for entry in transport.acked] == [
            "same-id",
            "same-id",
        ]


class TestSignalShutdownAtomicity:
    """OJS-PY-052: signal shutdown must atomically publish TERMINATE.

    The public ``state`` transition to ``TERMINATE`` and the shutdown
    event/drain must happen as one atomic step, and once shutdown has been
    requested, a stale "quiet"/"running" heartbeat directive that was
    already in flight must not be able to overwrite ``TERMINATE``.
    """

    async def test_stop_publishes_terminate_before_drain_completes(self) -> None:
        """`state` must read TERMINATE immediately, not only after drain."""
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job()])
        entered = asyncio.Event()
        release = asyncio.Event()

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
            grace_period=5.0,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            entered.set()
            await release.wait()
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.wait_for(entered.wait(), timeout=1)

        await worker.stop()
        # `stop()` returns as soon as `_request_termination` runs; the
        # active execution above is still draining (blocked on `release`)
        # at this point, so the state must already read TERMINATE rather
        # than lagging until the drain finishes.
        assert worker.state == WorkerState.TERMINATE
        assert not task.done()

        release.set()
        await _await_worker(task)
        assert worker.state == WorkerState.IDLE

    async def test_heartbeat_guard_prevents_stale_quiet_from_overwriting_terminate(
        self,
    ) -> None:
        """A `quiet` directive already in flight cannot undo TERMINATE.

        Simulates the exact race: a heartbeat request is dispatched and
        the server's response is still pending when shutdown is requested
        (by a signal or `stop()`); the response then resolves with a
        stale "quiet" directive that must be ignored.
        """
        heartbeat_started = asyncio.Event()
        release_heartbeat = asyncio.Event()

        class BlockingHeartbeatTransport(FakeTransport):
            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                heartbeat_started.set()
                await release_heartbeat.wait()
                return {"state": "quiet", "jobs_extended": []}

        transport = BlockingHeartbeatTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=60,
            heartbeat_interval=0.01,
        )
        run_state = WorkerRunState(worker._concurrency)

        heartbeat_task = asyncio.create_task(worker._heartbeat_loop(run_state))
        await asyncio.wait_for(heartbeat_started.wait(), timeout=1)

        # Shutdown is requested (signal/stop) WHILE the heartbeat response
        # above is still pending.
        worker._request_termination(run_state)
        assert worker.state == WorkerState.TERMINATE

        # The stale, already-in-flight heartbeat now resolves with "quiet".
        release_heartbeat.set()
        await asyncio.wait_for(heartbeat_task, timeout=1)

        assert worker.state == WorkerState.TERMINATE

    async def test_heartbeat_guard_prevents_stale_running_from_overwriting_terminate(
        self,
    ) -> None:
        """Same race as above, but with a stale "running" directive."""
        heartbeat_started = asyncio.Event()
        release_heartbeat = asyncio.Event()

        class BlockingHeartbeatTransport(FakeTransport):
            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                heartbeat_started.set()
                await release_heartbeat.wait()
                return {"state": "running", "jobs_extended": []}

        transport = BlockingHeartbeatTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=60,
            heartbeat_interval=0.01,
        )
        run_state = WorkerRunState(worker._concurrency)

        heartbeat_task = asyncio.create_task(worker._heartbeat_loop(run_state))
        await asyncio.wait_for(heartbeat_started.wait(), timeout=1)

        worker._request_termination(run_state)
        assert worker.state == WorkerState.TERMINATE

        release_heartbeat.set()
        await asyncio.wait_for(heartbeat_task, timeout=1)

        assert worker.state == WorkerState.TERMINATE

    async def test_heartbeat_directives_still_apply_before_shutdown_requested(
        self,
    ) -> None:
        """Regression guard: the race fix must not break normal operation.

        Without a pending shutdown, "quiet"/"running" directives must
        still transition `state` exactly as before.
        """
        first_response_consumed = asyncio.Event()
        release_second_response = asyncio.Event()

        class GatedHeartbeatTransport(FakeTransport):
            async def heartbeat(
                self,
                worker_id: str,
                active_jobs: list[str] | None = None,
                visibility_timeout_ms: int | None = None,
            ) -> dict[str, object]:
                if not first_response_consumed.is_set():
                    first_response_consumed.set()
                    return {"state": "quiet", "jobs_extended": []}
                await release_second_response.wait()
                return {"state": "running", "jobs_extended": []}

        transport = GatedHeartbeatTransport()
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=60,
            heartbeat_interval=0.01,
        )
        run_state = WorkerRunState(worker._concurrency)

        heartbeat_task = asyncio.create_task(worker._heartbeat_loop(run_state))
        await asyncio.wait_for(first_response_consumed.wait(), timeout=1)
        for _ in range(50):
            if worker.state == WorkerState.QUIET:
                break
            await asyncio.sleep(0.01)
        assert worker.state == WorkerState.QUIET

        release_second_response.set()
        for _ in range(50):
            if worker.state == WorkerState.RUNNING:
                break
            await asyncio.sleep(0.01)
        assert worker.state == WorkerState.RUNNING

        run_state.request_shutdown()
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(heartbeat_task, timeout=1)

    async def test_real_sigterm_atomically_publishes_terminate_state(self) -> None:
        """End-to-end: an actual OS SIGTERM publishes TERMINATE atomically.

        Delivers a real signal to the current process (which asyncio's
        event loop dispatches safely via `add_signal_handler`) rather than
        only exercising the callback indirectly through `stop()`.
        """
        transport = FakeTransport()
        transport.set_fetch_jobs([_make_job()])
        entered = asyncio.Event()
        release = asyncio.Event()

        worker = ojs.Worker(
            "http://localhost:8080",
            transport=transport,
            poll_interval=0.01,
            heartbeat_interval=60,
            grace_period=5.0,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            entered.set()
            await release.wait()
            return "ok"

        task = asyncio.create_task(worker.start())
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert worker.state == WorkerState.RUNNING

        os.kill(os.getpid(), signal.SIGTERM)
        # Give the event loop a turn to process the delivered signal via
        # its self-pipe/wakeup mechanism and run the scheduled callback.
        for _ in range(50):
            if worker.state == WorkerState.TERMINATE:
                break
            await asyncio.sleep(0.01)

        assert worker.state == WorkerState.TERMINATE
        # The active execution is still draining at this point.
        assert not task.done()

        release.set()
        await _await_worker(task)
        assert worker.state == WorkerState.IDLE


class TestSignalCustody:
    async def test_previous_signal_handlers_are_restored(self) -> None:
        previous = {
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
            signal.SIGINT: signal.getsignal(signal.SIGINT),
        }
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=FakeTransport(),
            poll_interval=0.01,
            heartbeat_interval=60,
        )

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        await _run_worker_briefly(worker)

        assert signal.getsignal(signal.SIGTERM) is previous[signal.SIGTERM]
        assert signal.getsignal(signal.SIGINT) is previous[signal.SIGINT]

    async def test_only_one_worker_can_own_signal_handlers(self) -> None:
        first = ojs.Worker(
            "http://localhost:8080",
            transport=FakeTransport(),
            poll_interval=60,
            heartbeat_interval=60,
        )
        second = ojs.Worker(
            "http://localhost:8080",
            transport=FakeTransport(),
            poll_interval=60,
            heartbeat_interval=60,
        )

        @first.register("test.echo")
        async def first_handler(ctx: ojs.JobContext) -> str:
            return "ok"

        @second.register("test.echo")
        async def second_handler(ctx: ojs.JobContext) -> str:
            return "ok"

        first_task = asyncio.create_task(first.start())
        await asyncio.sleep(0.02)
        with pytest.raises(RuntimeError, match="owns the process signal handlers"):
            await second.start()
        await first.stop()
        await _await_worker(first_task)

    async def test_signal_installation_can_be_disabled(self) -> None:
        workers = [
            ojs.Worker(
                "http://localhost:8080",
                transport=FakeTransport(),
                poll_interval=60,
                heartbeat_interval=60,
                install_signal_handlers=False,
            )
            for _ in range(2)
        ]
        for worker in workers:

            @worker.register("test.echo")
            async def handler(ctx: ojs.JobContext) -> str:
                return "ok"

        tasks = [asyncio.create_task(worker.start()) for worker in workers]
        await asyncio.sleep(0.02)
        for worker in workers:
            await worker.stop()
        await asyncio.gather(*tasks)


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
