# ojs-python-sdk

The official Python SDK for [Open Job Spec (OJS)](https://openjobspec.org) -- a language-agnostic standard for background job processing.

## Features

- **Async-first** -- built on `asyncio` with `httpx` for HTTP transport
- **Full OJS coverage** -- jobs, retries, workflows, middleware, events
- **Type-safe** -- complete type hints for all public APIs
- **Structured concurrency** -- worker uses `asyncio.TaskGroup` (Python 3.11+)
- **Middleware** -- enqueue and execution middleware with `next()` pattern
- **Sync wrapper** -- `SyncClient` for scripts that don't use asyncio

## Installation

```bash
pip install openjobspec
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
    retry=ojs.RetryPolicy(
        max_attempts=5,
        initial_interval="PT2S",
        backoff_coefficient=2.0,
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

### Workflows

```python
# Sequential chain
wf = await client.workflow(
    ojs.chain("onboarding", [
        ojs.JobRequest(type="user.create", args=["user@example.com"]),
        ojs.JobRequest(type="email.send", args=["user@example.com", "welcome"]),
    ])
)

# Parallel group
wf = await client.workflow(
    ojs.group("resize-images", [
        ojs.JobRequest(type="image.resize", args=["img.jpg", "small"]),
        ojs.JobRequest(type="image.resize", args=["img.jpg", "medium"]),
        ojs.JobRequest(type="image.resize", args=["img.jpg", "large"]),
    ])
)

# Batch with callbacks
wf = await client.workflow(
    ojs.batch("data-import", [
        ojs.JobRequest(type="import.chunk", args=[1, 1000]),
        ojs.JobRequest(type="import.chunk", args=[1001, 2000]),
    ],
    on_complete=ojs.JobRequest(type="import.finalize", args=[]),
    on_success=ojs.JobRequest(type="notify.done", args=[]),
    )
)
```

### Middleware

```python
# Enqueue middleware (client-side)
@client.enqueue_middleware
async def add_trace_id(request, next):
    request.meta = request.meta or {}
    request.meta["trace_id"] = generate_trace_id()
    return await next(request)

# Execution middleware (worker-side)
@worker.middleware
async def timing(ctx: ojs.JobContext, next):
    start = time.monotonic()
    result = await next()
    duration = time.monotonic() - start
    logger.info(f"{ctx.job_type} took {duration:.3f}s")
    return result
```

### Sync Client

```python
with ojs.SyncClient("http://localhost:8080") as client:
    job = client.enqueue("email.send", ["user@example.com", "welcome"])
```

## Requirements

- Python 3.11+
- An OJS-compatible server (e.g., [ojs-backend-redis](https://github.com/openjobspec/ojs-backend-redis))

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

## License

Apache 2.0 -- see [LICENSE](LICENSE).
