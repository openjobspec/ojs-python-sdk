"""OpenJobSpec Python SDK.

The official Python SDK for Open Job Spec (OJS), providing
async-first client and worker implementations.

Usage::

    import ojs

    # Producer
    async with ojs.Client("http://localhost:8080") as client:
        job = await client.enqueue("email.send", ["user@example.com", "welcome"])

    # Consumer
    worker = ojs.Worker("http://localhost:8080", queues=["email"])

    @worker.register("email.send")
    async def handle_email(ctx: ojs.JobContext):
        to, template = ctx.args[0], ctx.args[1]
        await send_email(to, template)

    await worker.start()
"""

from ojs.client import Client, SyncClient
from ojs.errors import (
    DuplicateJobError,
    JobNotFoundError,
    OJSAPIError,
    OJSConnectionError,
    OJSError,
    OJSTimeoutError,
    OJSValidationError,
    QueuePausedError,
    RateLimitedError,
)
from ojs.events import Event, EventType
from ojs.job import Job, JobContext, JobRequest, JobState, UniquePolicy
from ojs.middleware import (
    EnqueueMiddleware,
    ExecutionMiddleware,
)
from ojs.queue import Queue, QueueStats
from ojs.retry import RetryPolicy
from ojs.worker import Worker
from ojs.workflow import (
    Workflow,
    WorkflowDefinition,
    WorkflowStep,
    batch,
    chain,
    group,
)

__version__ = "0.1.0"
__ojs_specversion__ = "1.0"

__all__ = [
    # Client
    "Client",
    "SyncClient",
    # Worker
    "Worker",
    # Core types
    "Job",
    "JobContext",
    "JobRequest",
    "JobState",
    "RetryPolicy",
    "UniquePolicy",
    # Queue
    "Queue",
    "QueueStats",
    # Workflow
    "Workflow",
    "WorkflowDefinition",
    "WorkflowStep",
    "chain",
    "group",
    "batch",
    # Events
    "Event",
    "EventType",
    # Middleware
    "EnqueueMiddleware",
    "ExecutionMiddleware",
    # Errors
    "OJSError",
    "OJSAPIError",
    "OJSConnectionError",
    "OJSTimeoutError",
    "OJSValidationError",
    "DuplicateJobError",
    "JobNotFoundError",
    "QueuePausedError",
    "RateLimitedError",
]
