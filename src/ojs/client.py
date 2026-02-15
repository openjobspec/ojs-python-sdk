"""OJS Client -- the producer-side API.

Provides async methods for enqueuing jobs, managing workflows,
and querying job/queue state.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ojs.errors import OJSError
from ojs.job import Job, JobRequest, JobState
from ojs.middleware import EnqueueMiddleware, EnqueueMiddlewareChain
from ojs.queue import Queue, QueueStats
from ojs.retry import RetryPolicy
from ojs.transport.base import Transport
from ojs.transport.http import HTTPTransport
from ojs.workflow import Workflow, WorkflowDefinition


class Client:
    """OJS client for enqueuing jobs and managing the job system.

    Usage::

        client = ojs.Client("http://localhost:8080")

        # Enqueue a job
        job = await client.enqueue("email.send", ["user@example.com", "welcome"])

        # Enqueue with options
        job = await client.enqueue(
            "email.send",
            [{"to": "user@example.com"}],
            queue="email",
            retry=ojs.RetryPolicy(max_attempts=5),
        )

        # Batch enqueue
        jobs = await client.enqueue_batch([
            ojs.JobRequest(type="email.send", args=["a@b.com"]),
            ojs.JobRequest(type="email.send", args=["c@d.com"]),
        ])

        # Close when done
        await client.close()

    Also works as an async context manager::

        async with ojs.Client("http://localhost:8080") as client:
            await client.enqueue("email.send", ["user@example.com"])
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._transport = transport or HTTPTransport(url, timeout=timeout, headers=headers)
        self._enqueue_middleware = EnqueueMiddlewareChain()

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # --- Enqueue Middleware ---

    def enqueue_middleware(self, fn: EnqueueMiddleware) -> EnqueueMiddleware:
        """Register an enqueue middleware (decorator).

        The middleware receives (request, next) and must call
        await next(request) to continue the chain.

        Usage::

            @client.enqueue_middleware
            async def add_trace_id(request, next):
                request.meta = request.meta or {}
                request.meta["trace_id"] = generate_trace_id()
                return await next(request)
        """
        self._enqueue_middleware.add(fn)
        return fn

    # --- Job Operations ---

    async def enqueue(
        self,
        job_type: str,
        args: list[Any] | None = None,
        *,
        queue: str = "default",
        meta: dict[str, Any] | None = None,
        priority: int = 0,
        timeout_ms: int | None = None,
        delay_until: str | None = None,
        expires_at: str | None = None,
        retry: RetryPolicy | None = None,
        unique: Any | None = None,
        tags: list[str] | None = None,
        schema: str | None = None,
    ) -> Job:
        """Enqueue a single job.

        Args:
            job_type: Dot-namespaced job type (e.g., "email.send").
            args: Positional arguments for the job handler. Must be JSON-native.
            queue: Target queue name. Default: "default".
            meta: Extensible key-value metadata.
            priority: Job priority (higher = more important).
            timeout_ms: Maximum execution time in milliseconds.
            delay_until: ISO 8601 timestamp for delayed execution.
            expires_at: ISO 8601 timestamp for job expiration.
            retry: Retry policy override.
            unique: Unique job / deduplication policy.
            tags: Tags for filtering and observability.
            schema: Schema URI for payload validation.

        Returns:
            The created Job with server-assigned ID and state.
        """
        request = JobRequest(
            type=job_type,
            args=args or [],
            queue=queue,
            meta=meta,
            priority=priority,
            timeout_ms=timeout_ms,
            delay_until=delay_until,
            expires_at=expires_at,
            retry=retry,
            unique=unique,
            tags=tags,
            schema=schema,
        )

        # In fake mode, record the enqueue without hitting the transport
        from ojs.testing import get_store

        store = get_store()
        if store is not None:
            fake_job = store.record_enqueue(
                job_type=job_type,
                args=args or [],
                queue=queue,
                meta=meta,
                options=request.to_dict().get("options", {}),
            )
            return Job(
                id=fake_job.id,
                type=fake_job.type,
                state=JobState.AVAILABLE,
                args=fake_job.args,
                queue=fake_job.queue,
                meta=fake_job.meta,
            )

        async def _push(req: JobRequest) -> Job | None:
            return await self._transport.push(req.to_dict())

        result = await self._enqueue_middleware.execute(request, _push)
        if result is None:
            raise OJSError("Enqueue middleware chain returned None unexpectedly")
        return result

    async def enqueue_batch(self, requests: list[JobRequest]) -> list[Job]:
        """Enqueue multiple jobs in a single atomic operation.

        Args:
            requests: List of JobRequest objects.

        Returns:
            List of created Jobs.
        """
        from ojs.testing import get_store

        store = get_store()
        if store is not None:
            jobs: list[Job] = []
            for req in requests:
                fake_job = store.record_enqueue(
                    job_type=req.type,
                    args=req.args,
                    queue=req.queue,
                    meta=req.meta,
                    options=req.to_dict().get("options", {}),
                )
                jobs.append(
                    Job(
                        id=fake_job.id,
                        type=fake_job.type,
                        state=JobState.AVAILABLE,
                        args=fake_job.args,
                        queue=fake_job.queue,
                        meta=fake_job.meta or {},
                    )
                )
            return jobs

        bodies = [r.to_dict() for r in requests]
        return await self._transport.push_batch(bodies)

    async def get_job(self, job_id: str) -> Job:
        """Get job details by ID.

        Args:
            job_id: The UUIDv7 job identifier.

        Returns:
            The full Job object.
        """
        return await self._transport.info(job_id)

    async def cancel_job(self, job_id: str) -> Job:
        """Cancel a job.

        Args:
            job_id: The UUIDv7 job identifier.

        Returns:
            The Job in cancelled state.
        """
        return await self._transport.cancel(job_id)

    # --- Queue Operations ---

    async def list_queues(self) -> list[Queue]:
        """List all known queues."""
        return await self._transport.list_queues()

    async def queue_stats(self, queue_name: str) -> QueueStats:
        """Get statistics for a specific queue."""
        return await self._transport.queue_stats(queue_name)

    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        """Pause a queue."""
        return await self._transport.pause_queue(queue_name)

    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        """Resume a paused queue."""
        return await self._transport.resume_queue(queue_name)

    # --- Workflow Operations ---

    async def workflow(self, definition: WorkflowDefinition) -> Workflow:
        """Create and start a workflow.

        Args:
            definition: The workflow definition (from chain(), group(), batch()).

        Returns:
            The created Workflow with server-assigned ID and state.
        """
        return await self._transport.create_workflow(definition)

    async def get_workflow(self, workflow_id: str) -> Workflow:
        """Get workflow status."""
        return await self._transport.get_workflow(workflow_id)

    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Cancel a workflow."""
        return await self._transport.cancel_workflow(workflow_id)

    # --- System ---

    async def health(self) -> dict[str, Any]:
        """Health check."""
        return await self._transport.health()

    async def close(self) -> None:
        """Close the client and release resources."""
        await self._transport.close()


class SyncClient:
    """Synchronous wrapper around the async Client.

    Convenience class for scripts and applications that don't use asyncio.

    Usage::

        client = ojs.SyncClient("http://localhost:8080")
        job = client.enqueue("email.send", ["user@example.com", "welcome"])
        client.close()
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._client = Client(url, timeout=timeout, headers=headers)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def enqueue(self, job_type: str, args: list[Any] | None = None, **kwargs: Any) -> Job:
        return self._get_loop().run_until_complete(self._client.enqueue(job_type, args, **kwargs))

    def enqueue_batch(self, requests: list[JobRequest]) -> list[Job]:
        return self._get_loop().run_until_complete(self._client.enqueue_batch(requests))

    def get_job(self, job_id: str) -> Job:
        return self._get_loop().run_until_complete(self._client.get_job(job_id))

    def cancel_job(self, job_id: str) -> Job:
        return self._get_loop().run_until_complete(self._client.cancel_job(job_id))

    def health(self) -> dict[str, Any]:
        return self._get_loop().run_until_complete(self._client.health())

    # --- Queue Operations ---

    def list_queues(self) -> list[Queue]:
        return self._get_loop().run_until_complete(self._client.list_queues())

    def queue_stats(self, queue_name: str) -> QueueStats:
        return self._get_loop().run_until_complete(self._client.queue_stats(queue_name))

    def pause_queue(self, queue_name: str) -> dict[str, Any]:
        return self._get_loop().run_until_complete(self._client.pause_queue(queue_name))

    def resume_queue(self, queue_name: str) -> dict[str, Any]:
        return self._get_loop().run_until_complete(self._client.resume_queue(queue_name))

    # --- Workflow Operations ---

    def workflow(self, definition: WorkflowDefinition) -> Workflow:
        return self._get_loop().run_until_complete(self._client.workflow(definition))

    def get_workflow(self, workflow_id: str) -> Workflow:
        return self._get_loop().run_until_complete(self._client.get_workflow(workflow_id))

    def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self._get_loop().run_until_complete(self._client.cancel_workflow(workflow_id))

    # --- Lifecycle ---

    def close(self) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.run_until_complete(self._client.close())
            self._loop.close()

    def __enter__(self) -> SyncClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
