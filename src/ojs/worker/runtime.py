"""Worker runtime for processing Open Job Specification jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any, TypeVar

from ojs.errors import OJSAPIError, OJSConnectionError
from ojs.job import Job, JobContext
from ojs.middleware import ExecutionMiddleware, ExecutionMiddlewareChain
from ojs.progress import _report_progress
from ojs.transport.base import Transport
from ojs.transport.capabilities import ProgressTransport, WorkerTransport
from ojs.transport.http import HTTPTransport
from ojs.worker.completion_reporter import Completed, CompletionReporter, Failed
from ojs.worker.execution_retry import ExecutionLease
from ojs.worker.lease_admission import LeasePermit
from ojs.worker.options import validate_worker_options
from ojs.worker.run_state import WorkerRunState
from ojs.worker.shutdown_coordinator import ShutdownCoordinator
from ojs.worker.signal_custodian import SignalCustodian

logger = logging.getLogger("ojs.worker")

ExecutionMiddlewareT = TypeVar("ExecutionMiddlewareT", bound=ExecutionMiddleware)
Handler = Callable[[JobContext], Coroutine[Any, Any, Any]]


class WorkerState(StrEnum):
    """Worker lifecycle state."""

    IDLE = "idle"
    RUNNING = "running"
    QUIET = "quiet"
    TERMINATE = "terminate"
    TERMINATING = "terminate"


class Worker:
    """OJS worker that fetches and processes jobs."""

    def __init__(
        self,
        url: str,
        *,
        queues: list[str] | None = None,
        concurrency: int = 10,
        poll_interval: float = 2.0,
        heartbeat_interval: float = 5.0,
        visibility_timeout_ms: int | None = None,
        visibility_timeout: float | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: Transport | None = None,
        grace_period: float = 25.0,
        install_signal_handlers: bool = True,
    ) -> None:
        resolved_visibility_timeout_ms = validate_worker_options(
            concurrency=concurrency,
            poll_interval=poll_interval,
            heartbeat_interval=heartbeat_interval,
            visibility_timeout_ms=visibility_timeout_ms,
            visibility_timeout=visibility_timeout,
            request_timeout=timeout,
            grace_period=grace_period,
        )

        self._queues = queues or ["default"]
        self._concurrency = concurrency
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
        self._visibility_timeout_ms = resolved_visibility_timeout_ms
        self._grace_period = grace_period
        selected_transport: Transport = transport or HTTPTransport(
            url,
            timeout=timeout,
            headers=headers,
        )
        self._transport: WorkerTransport = selected_transport
        self._progress_transport: ProgressTransport = selected_transport
        self._worker_id = str(uuid.uuid4())

        self._handlers: dict[str, Handler] = {}
        self._execution_middleware = ExecutionMiddlewareChain()
        self._state = WorkerState.IDLE
        self._run_state: WorkerRunState | None = None
        self._signal_custodian = SignalCustodian(enabled=install_signal_handlers)

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def state(self) -> WorkerState:
        return self._state

    def register(self, job_type: str) -> Callable[[Handler], Handler]:
        """Register a handler for a job type."""

        def decorator(fn: Handler) -> Handler:
            if job_type in self._handlers:
                logger.warning("Overwriting handler for job type: %s", job_type)
            self._handlers[job_type] = fn
            return fn

        return decorator

    def handler(self, job_type: str, fn: Handler) -> None:
        """Register a handler using the historical non-decorator API."""
        self._handlers[job_type] = fn

    def middleware(self, fn: ExecutionMiddlewareT) -> ExecutionMiddlewareT:
        """Register execution middleware."""
        self._execution_middleware.add(fn)
        return fn

    async def start(self) -> None:
        """Start processing jobs until stopped or terminated."""
        if self._run_state is not None:
            raise RuntimeError("worker is already running")
        if not self._handlers:
            logger.warning("Worker started with no registered handlers")

        run_state = WorkerRunState(self._concurrency)
        self._run_state = run_state
        self._state = WorkerState.RUNNING
        logger.info(
            "Worker %s started, queues=%s, concurrency=%d",
            self._worker_id,
            self._queues,
            self._concurrency,
        )

        coordinator = ShutdownCoordinator(run_state, self._grace_period)
        try:
            self._signal_custodian.install(lambda: self._request_termination(run_state))
            await coordinator.run(
                self._fetch_loop(run_state),
                self._heartbeat_loop(run_state),
            )
        finally:
            run_state.request_shutdown()
            self._signal_custodian.restore()
            self._state = WorkerState.IDLE
            self._run_state = None
            logger.info("Worker %s stopped", self._worker_id)

    async def stop(self) -> None:
        """Request graceful shutdown of the current run."""
        run_state = self._run_state
        if run_state is None:
            return
        self._request_termination(run_state)

    def _request_termination(self, run_state: WorkerRunState) -> None:
        """Atomically publish TERMINATE and request shutdown/drain.

        This is the single choke point for every shutdown trigger — an OS
        signal, an explicit ``stop()`` call, and a server "terminate"
        heartbeat directive all route through here. Both statements are
        plain, synchronous (non-``await``) assignments, so from the event
        loop's perspective they execute as one atomic step: there is no
        ``await`` point between publishing the public ``TERMINATE`` state
        and setting the shutdown event, so no concurrently scheduled
        callback (in particular, a heartbeat response already in flight
        when a signal arrives) can observe the shutdown event set while
        ``state`` still reads a pre-shutdown value, or vice versa.

        Once shutdown has been requested this way, ``TERMINATE`` is a
        terminal, one-way state: ``_heartbeat_loop`` guards its own
        "quiet"/"running" directive handling behind
        ``run_state.shutdown.is_set()`` so a stale, already-in-flight
        heartbeat response cannot overwrite ``TERMINATE`` after the fact.
        """
        self._state = WorkerState.TERMINATE
        run_state.request_shutdown()

    async def _fetch_loop(self, run_state: WorkerRunState) -> None:
        while not run_state.shutdown.is_set():
            if self._state == WorkerState.QUIET:
                await run_state.wait_or_timeout(self._poll_interval)
                continue

            permits = await run_state.admission.reserve_available()
            if not permits:
                await run_state.wait_or_timeout(self._poll_interval)
                continue

            jobs: list[Job] = []
            used_permits = 0
            try:
                jobs = await self._transport.fetch(
                    queues=self._queues,
                    count=len(permits),
                    worker_id=self._worker_id,
                    visibility_timeout_ms=self._visibility_timeout_ms,
                )
                admitted = jobs[: len(permits)]
                for job, permit in zip(admitted, permits, strict=False):
                    self._start_execution(job, permit, run_state)
                    used_permits += 1
                for surplus_job in jobs[len(permits) :]:
                    await self._reject_surplus_lease(surplus_job)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error fetching jobs")
            finally:
                for permit in permits[used_permits:]:
                    run_state.admission.release(permit)

            if not jobs:
                await run_state.wait_or_timeout(self._poll_interval)

    def _start_execution(
        self,
        job: Job,
        permit: LeasePermit,
        run_state: WorkerRunState,
    ) -> None:
        lease = ExecutionLease(self._visibility_timeout_ms)
        task = asyncio.create_task(
            self._run_execution(job, permit, lease, run_state),
            name=f"ojs-job-{permit.token}",
        )
        run_state.executions.register(
            job_id=job.id,
            task=task,
            permit=permit,
            lease=lease,
        )

    async def _run_execution(
        self,
        job: Job,
        permit: LeasePermit,
        lease: ExecutionLease,
        run_state: WorkerRunState,
    ) -> None:
        try:
            await self._process_job(job, lease=lease)
        finally:
            run_state.executions.complete(permit.token)

    async def _reject_surplus_lease(self, job: Job) -> None:
        logger.error(
            "Backend returned job %s beyond requested worker capacity",
            job.id,
        )
        reporter = CompletionReporter(self._transport, job.id)
        await reporter.report(
            Failed(
                {
                    "code": "worker_over_capacity",
                    "message": "Backend returned more leases than requested",
                    "retryable": True,
                }
            )
        )

    async def _process_job(
        self,
        job: Job,
        *,
        lease: ExecutionLease | None = None,
    ) -> None:
        logger.info("Processing job %s type=%s", job.id, job.type)
        reporter = CompletionReporter(self._transport, job.id)

        handler = self._handlers.get(job.type)
        if handler is None:
            await reporter.report(
                Failed(
                    {
                        "code": "unknown_job_type",
                        "message": f"No handler registered for job type: {job.type}",
                        "retryable": False,
                    }
                )
            )
            return

        context = JobContext(
            job=job,
            attempt=max(1, job.attempt),
        )
        context._bind_runtime(
            transport=self._transport,
            retry_sleep=lease.sleep_for_retry if lease is not None else None,
            lease_remaining=(lambda: lease.remaining) if lease is not None else None,
            progress_reporter=lambda percentage, message, data: _report_progress(
                self._progress_transport,
                job.id,
                percentage,
                message,
                data,
            ),
        )

        try:
            result = await self._execution_middleware.execute(context, handler)
        except asyncio.CancelledError:
            await reporter.report(
                Failed(
                    {
                        "code": "cancelled",
                        "message": "Job cancelled during shutdown",
                        "retryable": True,
                    }
                )
            )
            raise
        except Exception as exc:
            logger.exception("Job %s failed", job.id)
            try:
                await reporter.report(
                    Failed(
                        {
                            "code": "handler_error",
                            "message": str(exc),
                            "retryable": True,
                        }
                    )
                )
            except Exception:
                logger.exception("Failed to deliver failure outcome for job %s", job.id)
            return

        try:
            await reporter.report(Completed(result))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to deliver completion outcome for job %s", job.id)

    async def _heartbeat_loop(self, run_state: WorkerRunState) -> None:
        backoff = 1.0
        while not run_state.shutdown.is_set():
            try:
                response = await self._transport.heartbeat(
                    worker_id=self._worker_id,
                    active_jobs=run_state.executions.active_job_ids(),
                    visibility_timeout_ms=self._visibility_timeout_ms,
                )
                extended = response.get("jobs_extended")
                extended_job_ids = (
                    {job_id for job_id in extended if isinstance(job_id, str)}
                    if isinstance(extended, list)
                    else set()
                )
                run_state.executions.extend_leases(
                    self._visibility_timeout_ms,
                    job_ids=extended_job_ids,
                )
                backoff = 1.0

                server_state = response.get("state")
                if server_state == "terminate":
                    self._request_termination(run_state)
                    return
                # A "quiet"/"running" directive must never downgrade a
                # worker that is already shutting down. Shutdown can be
                # requested concurrently (an OS signal, or an explicit
                # `stop()` call) while this heartbeat request was already
                # in flight; without this guard, the stale response
                # processed here could overwrite the just-published
                # TERMINATE state with QUIET/RUNNING after the fact.
                elif not run_state.shutdown.is_set():
                    if server_state == "quiet":
                        self._state = WorkerState.QUIET
                    elif server_state == "running":
                        self._state = WorkerState.RUNNING
            except asyncio.CancelledError:
                raise
            except (OJSConnectionError, OJSAPIError):
                logger.warning("Heartbeat failed, retrying in %.1fs", backoff)
                if await run_state.wait_or_timeout(backoff):
                    return
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception:
                logger.exception("Unexpected heartbeat error")

            if await run_state.wait_or_timeout(self._heartbeat_interval):
                return


__all__ = ["Handler", "Worker", "WorkerState"]
