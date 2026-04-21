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

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from types import ModuleType
from typing import TYPE_CHECKING, cast

from ojs._exports import LAZY_ATTRIBUTES, LAZY_MODULES
from ojs._version import __version__ as _source_version
from ojs.client import Client, SyncClient
from ojs.durable import DurableContext
from ojs.error_codes import ErrorCodeEntry, lookup_by_canonical_code, lookup_by_code
from ojs.errors import (
    DuplicateJobError,
    JobExecutionTimeout,
    JobNotFoundError,
    OJSAPIError,
    OJSCapabilityError,
    OJSConnectionError,
    OJSError,
    OJSTimeoutError,
    OJSValidationError,
    QueuePausedError,
    RateLimitedError,
    RateLimitInfo,
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

if TYPE_CHECKING:
    from ojs import agent, attest, ml, otel, recorder, serverless, subscribe
    from ojs.encryption import (
        EncryptionCodec,
        StaticKeyProvider,
        decryption_middleware,
        encryption_middleware,
    )

try:
    __version__ = version("openjobspec")
except PackageNotFoundError:
    __version__ = _source_version

__ojs_specversion__ = "1.0"

__all__ = [
    "Client",
    "DuplicateJobError",
    "DurableContext",
    "EncryptionCodec",
    "EnqueueMiddleware",
    "ErrorCodeEntry",
    "Event",
    "EventType",
    "ExecutionMiddleware",
    "Job",
    "JobContext",
    "JobExecutionTimeout",
    "JobNotFoundError",
    "JobRequest",
    "JobState",
    "OJSAPIError",
    "OJSCapabilityError",
    "OJSConnectionError",
    "OJSError",
    "OJSTimeoutError",
    "OJSValidationError",
    "Queue",
    "QueuePausedError",
    "QueueStats",
    "RateLimitInfo",
    "RateLimitedError",
    "RetryConfig",
    "RetryPolicy",
    "StaticKeyProvider",
    "SyncClient",
    "UniquePolicy",
    "Worker",
    "WorkerState",
    "Workflow",
    "WorkflowDefinition",
    "WorkflowStep",
    "__ojs_specversion__",
    "__version__",
    "agent",
    "attest",
    "batch",
    "chain",
    "decryption_middleware",
    "encryption_middleware",
    "group",
    "lookup_by_canonical_code",
    "lookup_by_code",
    "ml",
    "otel",
    "recorder",
    "report_progress",
    "serverless",
    "subscribe",
]


def __getattr__(name: str) -> object | ModuleType:
    module_name = LAZY_MODULES.get(name)
    if module_name is not None:
        module = import_module(module_name)
        globals()[name] = module
        return module

    target = LAZY_ATTRIBUTES.get(name)
    if target is not None:
        attribute_module, attribute_name = target
        value = getattr(import_module(attribute_module), attribute_name)
        globals()[name] = value
        return cast(object, value)
    raise AttributeError(f"module 'ojs' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
