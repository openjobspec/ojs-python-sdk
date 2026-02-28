# ojs-python-sdk

[![CI](https://github.com/openjobspec/ojs-python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/openjobspec/ojs-python-sdk/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/openjobspec)](https://pypi.org/project/openjobspec/)
[![Python versions](https://img.shields.io/pypi/pyversions/openjobspec)](https://pypi.org/project/openjobspec/)
[![License](https://img.shields.io/github/license/openjobspec/ojs-python-sdk)](LICENSE)

The official Python SDK for [Open Job Spec (OJS)](https://openjobspec.org) -- a vendor-neutral, language-agnostic specification for background job processing.

> **🚀 Try it now:** [Open in Playground](https://playground.openjobspec.org?lang=python) · [Run on CodeSandbox](https://codesandbox.io/p/sandbox/openjobspec-python-quickstart) · [Docker Quickstart](https://github.com/openjobspec/openjobspec/blob/main/docker-compose.quickstart.yml)

## Features

- **Async-first** -- built on `asyncio` with `httpx` for HTTP transport
- **Full OJS coverage** -- jobs, retries, workflows, middleware, events, cron, dead-letter queues
- **Type-safe** -- complete type hints for all public APIs; strict `mypy` compatible
- **Structured concurrency** -- worker uses `asyncio.TaskGroup` (Python 3.11+)
- **Middleware** -- enqueue (client-side) and execution (worker-side) middleware with `next()` pattern
- **Sync wrapper** -- `SyncClient` for scripts and applications that don't use asyncio
- **Single dependency** -- only `httpx`; OpenTelemetry is opt-in
- **Testing built in** -- `fake_mode()` context manager for unit tests without a running server

## Architecture

### Client -> Server Flow

```
  Application          ojs.Client          HTTP Transport        OJS Server
      |                    |                     |                    |
      |  enqueue(          |                     |                    |
      |    "email.send",   |                     |                    |
      |    args)           |                     |                    |
      |------------------->|                     |                    |
      |                    |  Validate type/args |                    |
      |                    |  Run enqueue mw     |                    |
      |                    |-------------------->|                    |
      |                    |                     | POST /ojs/v1/jobs  |
      |                    |                     | application/       |
      |                    |                     |  openjobspec+json  |
      |                    |                     |------------------->|
      |                    |                     |   201 Created      |
      |                    |                     |<-------------------|
      |                    |      Job            |                    |
      |                    |<--------------------|                    |
      |       Job          |                     |                    |
      |<-------------------|                     |                    |
```

### Worker Lifecycle

```
                        +-------------------+
                        |                   |
            start() --> |     RUNNING       |<-------+
                        |  (fetch + process)|        |
                        +--------+----------+        |
                                 |                   |
                    Server: quiet|    Server: running |
                                 v                   |
                        +--------+----------+        |
                        |                   |--------+
                        |      QUIET        |
                        |  (no new fetches) |
                        +--------+----------+
                                 |
               Server: terminate | / ctx.Done() / SIGTERM
                                 v
                        +--------+----------+
                        |                   |
                        |    TERMINATE      |
                        | (drain active,    |
                        |  25s grace period)|
                        +--------+----------+
                                 |
                                 v
                              [IDLE]
```

### Middleware Chain (Onion Model)

```
  Job Fetched --> [ Middleware 1 before ] --> [ Middleware 2 before ] --> [ Handler ]
                                                                            |
  ACK / NACK <-- [ Middleware 1 after  ] <-- [ Middleware 2 after  ] <------+
```

## Installation

```bash
pip install openjobspec
```

For OpenTelemetry instrumentation:

```bash
pip install openjobspec opentelemetry-api
```

For development (tests, linting, type checking):

```bash
pip install -e ".[dev]"
```

## Quick Start

### Enqueue a Job (Producer)

```python
import asyncio
import ojs

async def main():
    async with ojs.Client("http://localhost:8080") as client:
        job = await client.enqueue(
            "email.send",
            ["user@example.com", "welcome"],
            queue="email",
        )
        print(f"Enqueued: {job.id}")

asyncio.run(main())
```

### Process Jobs (Worker)

```python
import asyncio
import ojs

worker = ojs.Worker(
    "http://localhost:8080",
    queues=["email", "default"],
    concurrency=10,
)

@worker.register("email.send")
async def handle_email(ctx: ojs.JobContext):
    to, template = ctx.args[0], ctx.args[1]
    # ... send the email ...
    return {"sent": True}

asyncio.run(worker.start())
```

### Enqueue with Options

```python
job = await client.enqueue(
    "email.send",
    [{"to": "user@example.com", "template": "welcome"}],
    queue="email",
    priority=10,
    retry=ojs.RetryPolicy(
        max_attempts=5,
        initial_interval="PT2S",
        backoff_coefficient=2.0,
    ),
    unique=ojs.UniquePolicy(
        keys=["type", "args"],
        period="PT1H",
        on_conflict="reject",
    ),
    tags=["onboarding"],
)
```

### Batch Enqueue

```python
jobs = await client.enqueue_batch([
    ojs.JobRequest(type="email.send", args=["a@b.com", "welcome"], queue="email"),
    ojs.JobRequest(type="email.send", args=["c@d.com", "welcome"], queue="email"),
])
```

## Client API Reference

### Job Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `enqueue` | `(job_type, args, *, queue, meta, priority, timeout_ms, delay_until, expires_at, retry, unique, tags, schema)` | `Job` | Enqueue a single job |
| `enqueue_batch` | `(requests: list[JobRequest])` | `list[Job]` | Enqueue multiple jobs atomically |
| `get_job` | `(job_id: str)` | `Job` | Get job details by ID |
| `cancel_job` | `(job_id: str)` | `Job` | Cancel a job |

### Queue Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `list_queues` | `()` | `list[Queue]` | List all known queues |
| `queue_stats` | `(queue_name: str)` | `QueueStats` | Get statistics for a queue |
| `pause_queue` | `(queue_name: str)` | `dict` | Pause a queue |
| `resume_queue` | `(queue_name: str)` | `dict` | Resume a paused queue |

### Workflow Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `workflow` | `(definition: WorkflowDefinition)` | `Workflow` | Create and start a workflow |
| `get_workflow` | `(workflow_id: str)` | `Workflow` | Get workflow status |
| `cancel_workflow` | `(workflow_id: str)` | `dict` | Cancel a workflow |

### Cron Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `list_cron_jobs` | `(limit, offset)` | `dict` | List registered cron jobs |
| `register_cron_job` | `(name, cron, job_type, args, *, timezone, queue, meta, priority, retry, tags)` | `dict` | Register a cron job |
| `unregister_cron_job` | `(name: str)` | `dict` | Unregister a cron job |

### Dead Letter Operations

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `list_dead_letter_jobs` | `(queue, limit, offset)` | `dict` | List dead-letter jobs |
| `retry_dead_letter_job` | `(job_id: str)` | `Job` | Re-enqueue a dead-letter job |
| `delete_dead_letter_job` | `(job_id: str)` | `dict` | Permanently delete a dead-letter job |

### Schema & System

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `list_schemas` | `(limit, offset)` | `dict` | List registered schemas |
| `register_schema` | `(uri, job_type, version, schema)` | `dict` | Register a schema |
| `get_schema` | `(uri: str)` | `dict` | Get a schema by URI |
| `delete_schema` | `(uri: str)` | `dict` | Delete a schema |
| `manifest` | `()` | `dict` | Get server capabilities |
| `health` | `()` | `dict` | Health check |
| `close` | `()` | `None` | Close client and release resources |

## Worker API Reference

### Constructor

```python
worker = ojs.Worker(
    "http://localhost:8080",
    queues=["email", "default"],    # Queues to subscribe to
    concurrency=10,                 # Max parallel jobs
    poll_interval=2.0,              # Seconds between fetch attempts
    heartbeat_interval=5.0,         # Seconds between heartbeats
    visibility_timeout_ms=30000,    # Job reservation period (ms)
    timeout=30.0,                   # HTTP request timeout (s)
    headers={"Authorization": "Bearer token"},
)
```

### Handler Registration

```python
# Decorator form
@worker.register("email.send")
async def handle_email(ctx: ojs.JobContext):
    to = ctx.args[0]
    await send_email(to)
    return {"sent": True}

# Non-decorator form
async def handle_export(ctx: ojs.JobContext):
    await export_data(ctx.args[0])

worker.handler("data.export", handle_export)
```

### JobContext Properties

| Property | Type | Description |
|----------|------|-------------|
| `ctx.job` | `Job` | The full job envelope |
| `ctx.job_id` | `str` | Shortcut for `ctx.job.id` |
| `ctx.job_type` | `str` | Shortcut for `ctx.job.type` |
| `ctx.args` | `list[Any]` | Shortcut for `ctx.job.args` |
| `ctx.meta` | `dict[str, Any]` | Shortcut for `ctx.job.meta` |
| `ctx.attempt` | `int` | Current attempt number (1-indexed) |
| `ctx.parent_results` | `list[Any]` | Results from upstream workflow steps |
| `ctx.is_cancelled` | `bool` | Whether this execution was cancelled |

### Worker Lifecycle

```python
# Start the worker (blocks until shutdown)
await worker.start()

# Programmatic shutdown
await worker.stop()
```

Signal handling is automatic: `SIGTERM` and `SIGINT` trigger graceful shutdown with a 25-second grace period for active jobs.

## Workflows

### Chain (Sequential)

Jobs execute one after another. Each job receives the result of the previous job.

```python
wf = await client.workflow(
    ojs.chain("onboarding", [
        ojs.JobRequest(type="user.create", args=["user@example.com"]),
        ojs.JobRequest(type="email.send", args=["user@example.com", "welcome"]),
        ojs.JobRequest(type="analytics.track", args=["signup"]),
    ])
)
print(f"Workflow {wf.id}: {wf.state}")
```

### Group (Parallel)

All jobs execute concurrently with no ordering guarantees.

```python
wf = await client.workflow(
    ojs.group("resize-images", [
        ojs.JobRequest(type="image.resize", args=["img.jpg", "small"]),
        ojs.JobRequest(type="image.resize", args=["img.jpg", "medium"]),
        ojs.JobRequest(type="image.resize", args=["img.jpg", "large"]),
    ])
)
```

### Batch (Parallel with Callbacks)

All jobs execute concurrently. Callback jobs fire when all jobs reach terminal states.

```python
wf = await client.workflow(
    ojs.batch("data-import", [
        ojs.JobRequest(type="import.chunk", args=[1, 1000]),
        ojs.JobRequest(type="import.chunk", args=[1001, 2000]),
        ojs.JobRequest(type="import.chunk", args=[2001, 3000]),
    ],
    on_complete=ojs.JobRequest(type="import.finalize", args=[]),
    on_success=ojs.JobRequest(type="notify.done", args=[]),
    on_failure=ojs.JobRequest(type="notify.failure", args=[]),
    )
)
```

### Workflow Status

```python
wf = await client.get_workflow(wf.id)
for step in wf.steps:
    print(f"  {step.id}: {step.state} (job_id={step.job_id})")
```

## Middleware

### Execution Middleware (Worker-Side)

Execution middleware wraps job handler invocations using the onion model. Each middleware receives a `JobContext` and a `next` callable.

```python
@worker.middleware
async def timing(ctx: ojs.JobContext, next):
    start = time.monotonic()
    result = await next()
    duration = time.monotonic() - start
    logger.info(f"{ctx.job_type} took {duration:.3f}s")
    return result
```

### Enqueue Middleware (Client-Side)

Enqueue middleware intercepts job requests before they reach the transport. Each middleware receives a `JobRequest` and a `next` callable.

```python
@client.enqueue_middleware
async def add_trace_id(request, next):
    request.meta = request.meta or {}
    request.meta["trace_id"] = generate_trace_id()
    return await next(request)

@client.enqueue_middleware
async def validate_args(request, next):
    if not request.args:
        raise ojs.OJSValidationError("args must not be empty")
    return await next(request)
```

### Writing Custom Middleware

A custom middleware is an async function with the signature `async def(ctx, next) -> Any`. Call `await next()` to invoke the next middleware or the handler. You can run logic before and after, modify the context, catch exceptions, or skip the handler entirely.

```python
async def error_reporter(ctx: ojs.JobContext, next):
    try:
        return await next()
    except Exception as exc:
        await report_to_sentry(exc, job_id=ctx.job_id)
        raise

worker.middleware(error_reporter)
```

### Built-in Middleware

The SDK ships with four ready-to-use middleware in `ojs.middleware`:

```python
from ojs.middleware.logging import logging_middleware
from ojs.middleware.timeout import timeout_middleware
from ojs.middleware.retry import retry_middleware
from ojs.middleware.metrics import MetricsRecorder, metrics_middleware
```

**Logging** -- structured logging of job start, completion, and failure with timing:

```python
import logging

worker.middleware(logging_middleware())
worker.middleware(logging_middleware(log_level=logging.DEBUG))
worker.middleware(logging_middleware(custom_logger=my_logger))
```

**Timeout** -- abort job execution if it exceeds a deadline (uses `asyncio.timeout`):

```python
worker.middleware(timeout_middleware(seconds=30))
```

**Retry** -- retry failed executions with exponential backoff and jitter:

```python
worker.middleware(retry_middleware(
    max_retries=3,
    base_delay=0.1,
    max_delay=30.0,
    jitter=True,
))
```

**Metrics** -- pluggable metrics recording via the `MetricsRecorder` protocol:

```python
class MyRecorder:
    def job_started(self, job_type: str, queue: str) -> None: ...
    def job_completed(self, job_type: str, queue: str, duration_s: float) -> None: ...
    def job_failed(self, job_type: str, queue: str, duration_s: float, error: Exception) -> None: ...

worker.middleware(metrics_middleware(MyRecorder()))
```

The `MetricsRecorder` protocol is backend-agnostic -- implement it for Prometheus, StatsD, Datadog, or any metrics system.

## Error Handling

### Exception Hierarchy

| Exception | Parent | Description |
|-----------|--------|-------------|
| `OJSError` | `Exception` | Base exception for all OJS SDK errors |
| `OJSAPIError` | `OJSError` | Error returned by the OJS server (has `status_code`, `code`, `retryable`) |
| `OJSConnectionError` | `OJSError` | Failed to connect to the OJS server |
| `OJSTimeoutError` | `OJSError` | Request to the OJS server timed out |
| `OJSValidationError` | `OJSError` | Client-side validation error |
| `DuplicateJobError` | `OJSAPIError` | Unique job constraint violated (409) |
| `JobNotFoundError` | `OJSAPIError` | Job not found (404) |
| `QueuePausedError` | `OJSAPIError` | Target queue is paused (422) |
| `RateLimitedError` | `OJSAPIError` | Rate limit exceeded (429); has `retry_after` and `rate_limit` metadata |

### Standard Error Codes

| Code | HTTP Status | Exception | Retryable |
|------|-------------|-----------|-----------|
| `duplicate` | 409 | `DuplicateJobError` | No |
| `not_found` | 404 | `JobNotFoundError` | No |
| `queue_paused` | 422 | `QueuePausedError` | Yes |
| `rate_limited` | 429 | `RateLimitedError` | Yes |

### Example Error Handling

```python
import ojs

async with ojs.Client("http://localhost:8080") as client:
    # Catch specific error types
    try:
        job = await client.enqueue(
            "email.send",
            ["user@example.com"],
            unique=ojs.UniquePolicy(keys=["type", "args"]),
        )
    except ojs.DuplicateJobError:
        print("Job already exists")
    except ojs.RateLimitedError as exc:
        print(f"Rate limited, retry after {exc.retry_after}s")
        if exc.rate_limit:
            print(f"  Remaining: {exc.rate_limit.remaining}/{exc.rate_limit.limit}")
    except ojs.QueuePausedError:
        print("Queue is paused")
    except ojs.JobNotFoundError:
        print("Job not found")

    # Catch the base API error to inspect structured details
    try:
        job = await client.get_job("nonexistent-id")
    except ojs.OJSAPIError as exc:
        print(f"Code: {exc.code}")
        print(f"Status: {exc.status_code}")
        print(f"Retryable: {exc.retryable}")
        print(f"Message: {exc.error.message}")

    # Catch transport-level errors
    try:
        job = await client.enqueue("email.send", ["user@example.com"])
    except ojs.OJSConnectionError:
        print("Cannot reach the OJS server")
    except ojs.OJSTimeoutError:
        print("Request timed out")
```

## Events

The SDK provides event type constants for the OJS event system:

```python
from ojs import Event, EventType

# Core job events
EventType.JOB_ENQUEUED      # "job.enqueued"
EventType.JOB_STARTED       # "job.started"
EventType.JOB_COMPLETED     # "job.completed"
EventType.JOB_FAILED        # "job.failed"

# Extended job events
EventType.JOB_RETRYING      # "job.retrying"
EventType.JOB_CANCELLED     # "job.cancelled"
EventType.JOB_DISCARDED     # "job.discarded"
EventType.JOB_HEARTBEAT     # "job.heartbeat"
EventType.JOB_SCHEDULED     # "job.scheduled"

# Workflow events
EventType.WORKFLOW_STARTED   # "workflow.started"
EventType.WORKFLOW_COMPLETED # "workflow.completed"
EventType.WORKFLOW_FAILED    # "workflow.failed"

# Cron events
EventType.CRON_TRIGGERED     # "cron.triggered"
EventType.CRON_SKIPPED       # "cron.skipped"

# Worker events
EventType.WORKER_STARTED     # "worker.started"
EventType.WORKER_STOPPED     # "worker.stopped"
EventType.WORKER_QUIET       # "worker.quiet"
```

Events follow the CloudEvents-inspired envelope with convenient property accessors:

```python
event = Event.from_dict(raw_event)
print(event.event)     # e.g., "job.completed"
print(event.job_id)    # e.g., "019..."
print(event.job_type)  # e.g., "email.send"
print(event.queue)     # e.g., "email"
print(event.state)     # e.g., "completed"
print(event.timestamp) # datetime object
```

## Testing

The SDK includes a built-in testing module that lets you write unit tests without a running OJS server. The `fake_mode()` context manager intercepts all `client.enqueue()` calls and records them in memory.

```python
import pytest
from ojs.testing import fake_mode, assert_enqueued, refute_enqueued, all_enqueued, clear_all

@pytest.fixture(autouse=True)
def ojs_testing():
    with fake_mode():
        yield
```

### Assertion Helpers

```python
async def test_signup_enqueues_welcome_email():
    client = ojs.Client("http://localhost:8080")

    await client.enqueue("email.send", ["user@example.com", "welcome"], queue="email")
    await client.enqueue("analytics.track", ["signup"])

    # Assert a job of a given type was enqueued
    assert_enqueued("email.send")

    # Assert with specific args, queue, or meta
    assert_enqueued("email.send", args=["user@example.com", "welcome"], queue="email")

    # Assert exact count
    assert_enqueued("email.send", count=1)

    # Assert a job was NOT enqueued
    refute_enqueued("billing.charge")

    # Retrieve all enqueued jobs for custom assertions
    email_jobs = all_enqueued(job_type="email.send")
    assert len(email_jobs) == 1
    assert email_jobs[0].args[0] == "user@example.com"

    # Filter by queue
    email_queue_jobs = all_enqueued(queue="email")
    assert len(email_queue_jobs) == 1
```

### Drain (Execute Enqueued Jobs)

```python
from ojs.testing import fake_mode, drain

def test_drain_processes_jobs():
    with fake_mode() as store:
        store.register_handler("email.send", lambda job: None)

        client = ojs.SyncClient("http://localhost:8080")
        client.enqueue("email.send", ["user@example.com"])

        processed = drain()
        assert processed == 1
```

### SyncClient for Tests

For test code that isn't async, use `SyncClient`:

```python
def test_sync_enqueue():
    with ojs.SyncClient("http://localhost:8080") as client:
        job = client.enqueue("email.send", ["user@example.com", "welcome"])
        assert job.id is not None
```

## OpenTelemetry

The SDK provides native OpenTelemetry instrumentation as an opt-in module (to keep the core dependency-free). Install `opentelemetry-api` to enable it:

```bash
pip install opentelemetry-api
```

```python
from ojs.otel import opentelemetry_middleware

# Use global tracer/meter providers
worker.middleware(opentelemetry_middleware())

# Or supply explicit providers
worker.middleware(opentelemetry_middleware(
    tracer_provider=my_tracer_provider,
    meter_provider=my_meter_provider,
))
```

The middleware creates a CONSUMER span for each job and records:

| Metric | Type | Description |
|--------|------|-------------|
| `ojs.job.completed` | Counter | Jobs completed successfully |
| `ojs.job.failed` | Counter | Jobs that failed |
| `ojs.job.duration` | Histogram (seconds) | Job execution duration |

Span attributes follow OTel semantic conventions:

| Attribute | Example |
|-----------|---------|
| `messaging.system` | `"ojs"` |
| `messaging.operation` | `"process"` |
| `ojs.job.type` | `"email.send"` |
| `ojs.job.id` | `"019..."` |
| `ojs.job.queue` | `"email"` |
| `ojs.job.attempt` | `1` |

## Configuration Reference

### Client Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | (required) | OJS server URL |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |
| `headers` | `dict[str, str]` | `None` | Additional HTTP headers (e.g., auth tokens) |

### Enqueue Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `queue` | `str` | `"default"` | Target queue name |
| `meta` | `dict[str, Any]` | `None` | Extensible key-value metadata |
| `priority` | `int` | `0` | Job priority (higher = more important) |
| `timeout_ms` | `int` | `None` | Maximum execution time in milliseconds |
| `delay_until` | `str` | `None` | ISO 8601 timestamp for delayed execution |
| `expires_at` | `str` | `None` | ISO 8601 timestamp for job expiration |
| `retry` | `RetryPolicy` | `None` | Retry policy override |
| `unique` | `UniquePolicy` | `None` | Deduplication policy |
| `tags` | `list[str]` | `None` | Tags for filtering and observability |
| `schema` | `str` | `None` | Schema URI for payload validation |

### RetryPolicy Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_attempts` | `int` | `3` | Total attempts including initial execution |
| `initial_interval` | `str` | `"PT1S"` | ISO 8601 duration before first retry |
| `backoff_coefficient` | `float` | `2.0` | Multiplier applied after each retry |
| `max_interval` | `str` | `"PT5M"` | ISO 8601 duration cap on retry delay |
| `jitter` | `bool` | `True` | Randomize delay to prevent thundering herd |
| `non_retryable_errors` | `list[str]` | `[]` | Error codes that must not trigger retry |

### Worker Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | (required) | OJS server URL |
| `queues` | `list[str]` | `["default"]` | Queue subscriptions (priority order) |
| `concurrency` | `int` | `10` | Maximum parallel jobs |
| `poll_interval` | `float` | `2.0` | Seconds between fetch requests when idle |
| `heartbeat_interval` | `float` | `5.0` | Seconds between heartbeat requests |
| `visibility_timeout_ms` | `int` | `30000` | Job reservation period in milliseconds |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |
| `headers` | `dict[str, str]` | `None` | Additional HTTP headers |

## Type Hints and mypy

The SDK ships with complete type annotations for all public APIs and is tested with `mypy --strict`. All dataclasses (`Job`, `JobRequest`, `RetryPolicy`, `UniquePolicy`, `JobContext`, etc.) are fully typed.

```bash
# Type check your application code
mypy src/

# The SDK configures strict mode in pyproject.toml:
# [tool.mypy]
# python_version = "3.11"
# strict = true
```

Middleware type aliases are exported for use in your own type annotations:

```python
from ojs.middleware import EnqueueMiddleware, ExecutionMiddleware

my_mw: ExecutionMiddleware = my_middleware_function
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (asyncio_mode = auto)
pytest

# Run tests with coverage
pytest --cov

# Type check (strict mode)
mypy src/

# Lint
ruff check src/ tests/
```

## Requirements

- Python 3.11+
- An OJS-compatible server (e.g., [ojs-backend-redis](https://github.com/openjobspec/ojs-backend-redis) or [ojs-backend-postgres](https://github.com/openjobspec/ojs-backend-postgres))

## OJS Spec Conformance

This SDK implements the [OJS v1.0](https://openjobspec.org) specification:

- **Layer 1 (Core)**: Job envelope, 8-state lifecycle, retry policies, unique jobs, workflows, middleware
- **Layer 2 (Wire Format)**: JSON encoding with `application/openjobspec+json` content type
- **Layer 3 (HTTP Binding)**: Full HTTP REST protocol binding (PUSH, FETCH, ACK, FAIL, BEAT, CANCEL, INFO)
- **Worker Protocol**: Three-state lifecycle (running/quiet/terminate), heartbeat, graceful shutdown

## Resources

- [OJS Specification](https://github.com/openjobspec/spec) -- the language-agnostic standard
- [OJS Playground](https://github.com/openjobspec/ojs-playground) -- interactive browser-based environment
- [openjobspec.org](https://openjobspec.org) -- documentation and guides

## Contributing

Contributions are welcome. Please see the [OJS Contributing Guide](https://github.com/openjobspec/spec/blob/main/CONTRIBUTING.md) for the specification RFC process and coding conventions.

For SDK development:

1. Fork and clone the repository
2. Install dev dependencies: `pip install -e ".[dev]"`
3. Run tests: `pytest`
4. Run type checks: `mypy src/`
5. Run linter: `ruff check src/ tests/`
6. Open a pull request

## License

Apache 2.0 -- see [LICENSE](LICENSE).


