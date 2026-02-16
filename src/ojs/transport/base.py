"""Abstract transport protocol for OJS.

Defines the interface that all transport implementations must satisfy.
"""

from __future__ import annotations

import abc
from typing import Any

from ojs.job import Job
from ojs.queue import Queue, QueueStats
from ojs.workflow import Workflow, WorkflowDefinition


class Transport(abc.ABC):
    """Abstract base class for OJS transports.

    A transport handles the wire-level communication with an OJS server.
    """

    # --- Job Operations ---

    @abc.abstractmethod
    async def push(self, body: dict[str, Any]) -> Job:
        """PUSH: Enqueue a single job.

        Args:
            body: The enqueue request body (type, args, options, etc.).

        Returns:
            The created Job with server-assigned ID and state.
        """

    @abc.abstractmethod
    async def push_batch(self, jobs: list[dict[str, Any]]) -> list[Job]:
        """PUSH (batch): Enqueue multiple jobs atomically.

        Args:
            jobs: List of enqueue request bodies.

        Returns:
            List of created Jobs.
        """

    @abc.abstractmethod
    async def info(self, job_id: str) -> Job:
        """INFO: Get job details by ID.

        Args:
            job_id: The UUIDv7 job identifier.

        Returns:
            The full Job object.
        """

    @abc.abstractmethod
    async def cancel(self, job_id: str) -> Job:
        """CANCEL: Cancel a job.

        Args:
            job_id: The UUIDv7 job identifier.

        Returns:
            The Job in cancelled state.
        """

    # --- Worker Operations ---

    @abc.abstractmethod
    async def fetch(
        self,
        queues: list[str],
        count: int = 1,
        worker_id: str | None = None,
        visibility_timeout_ms: int = 30000,
    ) -> list[Job]:
        """FETCH: Dequeue jobs for processing.

        Args:
            queues: Ordered list of queues to fetch from.
            count: Maximum number of jobs to fetch.
            worker_id: Identifier for the worker process.
            visibility_timeout_ms: Reservation period in milliseconds.

        Returns:
            List of fetched Jobs (may be empty).
        """

    @abc.abstractmethod
    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        """ACK: Acknowledge successful completion.

        Args:
            job_id: The UUIDv7 job identifier.
            result: Optional result data from the handler.

        Returns:
            Acknowledgement response data.
        """

    @abc.abstractmethod
    async def nack(self, job_id: str, error: dict[str, Any]) -> dict[str, Any]:
        """FAIL: Report job failure with error data.

        Args:
            job_id: The UUIDv7 job identifier.
            error: Structured error information.

        Returns:
            Failure response data (state, next_attempt_at, etc.).
        """

    @abc.abstractmethod
    async def heartbeat(
        self,
        worker_id: str,
        active_jobs: list[str] | None = None,
        visibility_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """BEAT: Worker heartbeat / extend visibility.

        Args:
            worker_id: Unique worker identifier.
            active_jobs: List of job IDs currently being processed.
            visibility_timeout_ms: Requested visibility extension.

        Returns:
            Heartbeat response (state directive, jobs_extended, etc.).
        """

    # --- Queue Operations ---

    @abc.abstractmethod
    async def list_queues(self) -> list[Queue]:
        """List all known queues."""

    @abc.abstractmethod
    async def queue_stats(self, queue_name: str) -> QueueStats:
        """Get statistics for a specific queue."""

    @abc.abstractmethod
    async def pause_queue(self, queue_name: str) -> dict[str, Any]:
        """Pause a queue."""

    @abc.abstractmethod
    async def resume_queue(self, queue_name: str) -> dict[str, Any]:
        """Resume a paused queue."""

    # --- Workflow Operations ---

    @abc.abstractmethod
    async def create_workflow(self, definition: WorkflowDefinition) -> Workflow:
        """Create and start a workflow."""

    @abc.abstractmethod
    async def get_workflow(self, workflow_id: str) -> Workflow:
        """Get workflow status."""

    @abc.abstractmethod
    async def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Cancel a workflow."""

    # --- Manifest ---

    @abc.abstractmethod
    async def manifest(self) -> dict[str, Any]:
        """Get server manifest (capabilities, extensions, endpoints)."""

    # --- Dead Letter Operations ---

    @abc.abstractmethod
    async def list_dead_letter_jobs(
        self,
        queue: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List dead-letter jobs.

        Args:
            queue: Optional queue filter.
            limit: Maximum number of jobs to return.
            offset: Pagination offset.

        Returns:
            Dict with 'jobs' list and 'pagination' metadata.
        """

    @abc.abstractmethod
    async def retry_dead_letter_job(self, job_id: str) -> Job:
        """Retry a dead-letter job.

        Args:
            job_id: The job identifier.

        Returns:
            The re-enqueued Job.
        """

    @abc.abstractmethod
    async def delete_dead_letter_job(self, job_id: str) -> dict[str, Any]:
        """Delete a dead-letter job permanently.

        Args:
            job_id: The job identifier.

        Returns:
            Empty dict on success (204).
        """

    # --- Cron Operations ---

    @abc.abstractmethod
    async def list_cron_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List registered cron jobs.

        Args:
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            Dict with 'cron_jobs' list and 'pagination' metadata.
        """

    @abc.abstractmethod
    async def register_cron_job(self, body: dict[str, Any]) -> dict[str, Any]:
        """Register a new cron job.

        Args:
            body: Cron job definition (name, cron, type, args, etc.).

        Returns:
            The created cron job info.
        """

    @abc.abstractmethod
    async def unregister_cron_job(self, name: str) -> dict[str, Any]:
        """Unregister a cron job by name.

        Args:
            name: The cron job name.

        Returns:
            Empty dict on success (204).
        """

    # --- Schema Operations ---

    @abc.abstractmethod
    async def list_schemas(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List registered schemas.

        Args:
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            Dict with 'schemas' list and 'pagination' metadata.
        """

    @abc.abstractmethod
    async def register_schema(self, body: dict[str, Any]) -> dict[str, Any]:
        """Register a new schema.

        Args:
            body: Schema definition (uri, type, version, schema).

        Returns:
            The created schema info.
        """

    @abc.abstractmethod
    async def get_schema(self, uri: str) -> dict[str, Any]:
        """Get a schema by URI.

        Args:
            uri: The schema URI (will be URL-encoded).

        Returns:
            The schema info.
        """

    @abc.abstractmethod
    async def delete_schema(self, uri: str) -> dict[str, Any]:
        """Delete a schema by URI.

        Args:
            uri: The schema URI (will be URL-encoded).

        Returns:
            Empty dict on success (204).
        """

    # --- Lifecycle ---

    @abc.abstractmethod
    async def health(self) -> dict[str, Any]:
        """Health check."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the transport and release resources."""
