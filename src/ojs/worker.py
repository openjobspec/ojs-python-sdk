"""OJS Worker -- the consumer-side API.

Provides an async worker that fetches jobs from queues, dispatches
them to registered handlers, and manages the full job lifecycle
including heartbeats, ack/nack, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import signal
import traceback
import uuid
from typing import Any, Callable

from ojs.job import Job, JobContext, JobHandler
from ojs.middleware import ExecutionMiddleware, ExecutionMiddlewareChain
from ojs.transport.base import Transport
from ojs.transport.http import HTTPTransport

logger = logging.getLogger("ojs.worker")


class WorkerState(enum.StrEnum):
    """Worker lifecycle states."""

    IDLE = "idle"
    RUNNING = "running"
    QUIET = "quiet"
    TERMINATE = "terminate"


class Worker:
    """OJS Worker that fetches and processes jobs.

    Usage::

        worker = ojs.Worker("http://localhost:8080", queues=["email", "default"])

        @worker.register("email.send")
        async def handle_email(ctx: ojs.JobContext):
            to = ctx.args[0]
            template = ctx.args[1]
            await send_email(to, template)
            return {"sent": True}

        @worker.middleware
        async def logging_mw(ctx: ojs.JobContext, next):
            logger.info(f"Processing {ctx.job_type} {ctx.job_id}")
            result = await next()
            logger.info(f"Completed {ctx.job_type} {ctx.job_id}")
            return result

        await worker.start()

    Signals:
        - SIGTERM: Begin graceful shutdown (terminate).
        - SIGINT: Begin graceful shutdown (terminate).
    """

    def __init__(
        self,
        url: str,
        *,
        queues: list[str] | None = None,
        concurrency: int = 10,
        poll_interval: float = 2.0,
        heartbeat_interval: float = 5.0,
        visibility_timeout_ms: int = 30000,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: Transport | None = None,
    ) -> None:
        """Initialize the worker.

        Args:
            url: The OJS server URL.
            queues: List of queues to fetch from. Default: ["default"].
            concurrency: Maximum concurrent job executions. Default: 10.
            poll_interval: Seconds between fetch requests when idle. Default: 2.0.
            heartbeat_interval: Seconds between heartbeat requests. Default: 5.0.
            visibility_timeout_ms: Job reservation period in ms. Default: 30000.
            timeout: HTTP request timeout in seconds. Default: 30.
            headers: Additional HTTP headers.
            transport: Optional pre-configured transport.
        """
        self._transport = transport or HTTPTransport(
            url, timeout=timeout, headers=headers
        )
        self._queues = queues or ["default"]
        self._concurrency = concurrency
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
        self._visibility_timeout_ms = visibility_timeout_ms

        self._handlers: dict[str, JobHandler] = {}
        self._execution_middleware = ExecutionMiddlewareChain()
        self._worker_id = f"worker_{uuid.uuid4().hex[:16]}"

        # Runtime state
        self._state = WorkerState.IDLE
        self._active_jobs: dict[str, asyncio.Task[Any]] = {}
        self._shutdown_event = asyncio.Event()
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def state(self) -> WorkerState:
        return self._state

    # --- Handler Registration ---

    def register(self, job_type: str) -> Callable[[JobHandler], JobHandler]:
        """Register a handler for a job type (decorator).

        Usage::

            @worker.register("email.send")
            async def handle_email(ctx: ojs.JobContext):
                ...
        """

        def decorator(fn: JobHandler) -> JobHandler:
            self._handlers[job_type] = fn
            return fn

        return decorator

    def handler(self, job_type: str, fn: JobHandler) -> None:
        """Register a handler for a job type (non-decorator form)."""
        self._handlers[job_type] = fn

    # --- Middleware Registration ---

    def middleware(self, fn: ExecutionMiddleware) -> ExecutionMiddleware:
        """Register an execution middleware (decorator).

        Usage::

            @worker.middleware
            async def my_middleware(ctx: ojs.JobContext, next):
                # before
                result = await next()
                # after
                return result
        """
        self._execution_middleware.add(fn)
        return fn

    # --- Worker Lifecycle ---

    async def start(self) -> None:
        """Start the worker.

        Runs the fetch loop, heartbeat loop, and processes jobs
        using asyncio.TaskGroup for structured concurrency.

        Blocks until shutdown is triggered (via signal or explicit stop).
        """
        self._state = WorkerState.RUNNING
        self._semaphore = asyncio.Semaphore(self._concurrency)

        # Install signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        logger.info(
            "Worker %s starting: queues=%s concurrency=%d",
            self._worker_id,
            self._queues,
            self._concurrency,
        )

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._fetch_loop())
                tg.create_task(self._heartbeat_loop())
                tg.create_task(self._wait_for_shutdown())
        except* Exception as eg:
            # TaskGroup propagates exceptions; log them
            for exc in eg.exceptions:
                if not isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
                    logger.error("Worker error: %s", exc)
        finally:
            self._state = WorkerState.IDLE
            logger.info("Worker %s stopped", self._worker_id)

    async def stop(self) -> None:
        """Trigger graceful shutdown."""
        self._state = WorkerState.TERMINATE
        self._shutdown_event.set()

    def _handle_signal(self, sig: signal.Signals) -> None:
        logger.info("Received signal %s, shutting down", sig.name)
        self._state = WorkerState.TERMINATE
        self._shutdown_event.set()

    async def _wait_for_shutdown(self) -> None:
        """Wait for the shutdown event, then cancel remaining tasks."""
        await self._shutdown_event.wait()

        # Wait for active jobs to finish (grace period)
        if self._active_jobs:
            logger.info(
                "Waiting for %d active jobs to complete...",
                len(self._active_jobs),
            )
            grace_period = 25.0  # OJS spec: 25s grace period
            try:
                await asyncio.wait_for(
                    self._wait_active_jobs(), timeout=grace_period
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Grace period expired, %d jobs still active",
                    len(self._active_jobs),
                )
                for task in self._active_jobs.values():
                    task.cancel()

        # Cancel sibling tasks in the TaskGroup
        raise asyncio.CancelledError

    async def _wait_active_jobs(self) -> None:
        while self._active_jobs:
            await asyncio.sleep(0.1)

    # --- Fetch Loop ---

    async def _fetch_loop(self) -> None:
        """Continuously fetch jobs from queues and dispatch them."""
        while self._state == WorkerState.RUNNING:
            try:
                if self._semaphore is None:
                    raise RuntimeError("Worker.start() must be called before fetch loop")
                await self._semaphore.acquire()

                if self._state != WorkerState.RUNNING:
                    self._semaphore.release()
                    break

                jobs = await self._transport.fetch(
                    queues=self._queues,
                    count=1,
                    worker_id=self._worker_id,
                    visibility_timeout_ms=self._visibility_timeout_ms,
                )

                if not jobs:
                    self._semaphore.release()
                    await asyncio.sleep(self._poll_interval)
                    continue

                for job in jobs:
                    task = asyncio.create_task(
                        self._process_job(job),
                        name=f"job-{job.id}",
                    )
                    self._active_jobs[job.id] = task
                    task.add_done_callback(self._make_done_callback(job.id))

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in fetch loop")
                await asyncio.sleep(self._poll_interval)

    def _make_done_callback(self, job_id: str) -> Callable[[asyncio.Task[Any]], None]:
        def _callback(task: asyncio.Task[Any]) -> None:
            self._job_done(job_id)
        return _callback

    def _job_done(self, job_id: str) -> None:
        self._active_jobs.pop(job_id, None)
        if self._semaphore:
            self._semaphore.release()

    # --- Job Processing ---

    async def _process_job(self, job: Job) -> None:
        """Process a single job through middleware and handler."""
        handler = self._handlers.get(job.type)
        if handler is None:
            logger.error("No handler registered for job type %r", job.type)
            await self._transport.nack(
                job.id,
                {
                    "code": "handler_error",
                    "message": f"No handler registered for job type '{job.type}'",
                    "retryable": False,
                },
            )
            return

        ctx = JobContext(job=job, attempt=job.attempt or 1)

        try:
            result = await self._execution_middleware.execute(ctx, handler)
            await self._transport.ack(job.id, result=result)
        except asyncio.CancelledError:
            logger.warning("Job %s cancelled", job.id)
            await self._transport.nack(
                job.id,
                {
                    "code": "cancelled",
                    "message": "Job execution was cancelled during worker shutdown",
                    "retryable": True,
                },
            )
        except Exception as exc:
            logger.exception("Job %s failed: %s", job.id, exc)
            await self._transport.nack(
                job.id,
                {
                    "code": "handler_error",
                    "message": str(exc),
                    "retryable": True,
                    "details": {"traceback": traceback.format_exc()},
                },
            )

    # --- Heartbeat Loop ---

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats to the OJS server."""
        while self._state in (WorkerState.RUNNING, WorkerState.QUIET):
            try:
                active_ids = list(self._active_jobs.keys())
                if active_ids or self._state == WorkerState.RUNNING:
                    response = await self._transport.heartbeat(
                        worker_id=self._worker_id,
                        active_jobs=active_ids,
                        visibility_timeout_ms=self._visibility_timeout_ms,
                    )

                    # Handle server-initiated state changes
                    server_state = response.get("state")
                    if server_state == "quiet" and self._state == WorkerState.RUNNING:
                        logger.info("Server requested quiet mode")
                        self._state = WorkerState.QUIET
                    elif server_state == "terminate":
                        logger.info("Server requested termination")
                        await self.stop()
                        return

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in heartbeat loop")

            await asyncio.sleep(self._heartbeat_interval)
