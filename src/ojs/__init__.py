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
from ojs.error_codes import ErrorCodeEntry
from ojs.error_codes import lookup_by_canonical_code, lookup_by_code
from ojs.errors import (
    DuplicateJobError,
    JobNotFoundError,
    OJSAPIError,
    OJSConnectionError,
    OJSError,
    OJSTimeoutError,
    OJSValidationError,
    QueuePausedError,
    RateLimitInfo,
    RateLimitedError,
)
from ojs.events import Event, EventType
from ojs.job import Job, JobContext, JobRequest, JobState, UniquePolicy
from ojs.middleware import (
    EnqueueMiddleware,
    ExecutionMiddleware,
)
from ojs.progress import report_progress
from ojs.queue import Queue, QueueStats
from ojs.retry import RetryPolicy
from ojs.transport.rate_limiter import RetryConfig
from ojs.worker import Worker, WorkerState
from ojs.workflow import (
    Workflow,
    WorkflowDefinition,
    WorkflowStep,
    batch,
    chain,
    group,
)
from ojs.durable import DurableContext
from ojs.encryption import (
    EncryptionCodec,
    StaticKeyProvider,
    encryption_middleware,
    decryption_middleware,
)

__version__ = "0.1.0"
__ojs_specversion__ = "1.0"

__all__ = [
    # Client
    "Client",
    "SyncClient",
    # Worker
    "Worker",
    "WorkerState",
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
    # Rate Limiting
    "RetryConfig",
    # Progress
    "report_progress",
    # Durable execution
    "DurableContext",
    # Encryption
    "EncryptionCodec",
    "StaticKeyProvider",
    "encryption_middleware",
    "decryption_middleware",
    # ML/AI Resource Extension (available via ojs.ml)
    # Serverless adapters (available via ojs.serverless)
    # Agent Substrate Protocol (available via ojs.agent)
    # Attestation (available via ojs.attest)
    # Recorder (available via ojs.recorder)
]

# Lazy imports for moonshot submodules — avoid import-time overhead
# for users who don't need them. Use: `from ojs.agent import AgentClient`
def __getattr__(name: str):
    if name == "agent":
        from ojs import agent as _agent
        return _agent
    if name == "attest":
        from ojs import attest as _attest
        return _attest
    if name == "recorder":
        from ojs import recorder as _recorder
        return _recorder
    raise AttributeError(f"module 'ojs' has no attribute {name!r}")
