"""Middleware example: client-side enqueue and worker-side execution middleware.

Demonstrates the composable middleware pattern with next(). Both enqueue
and execution middleware use an onion model where first-registered middleware
executes outermost.

Execution order for worker middleware [logging, metrics, tracing]:
    logging.before → metrics.before → tracing.before → handler
    → tracing.after → metrics.after → logging.after

Prerequisites:
    An OJS-compatible server running at http://localhost:8080
"""

import asyncio
import logging
import time
import uuid

import ojs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---- Client-side enqueue middleware ----

client = ojs.Client("http://localhost:8080")


@client.enqueue_middleware
async def trace_context_middleware(request, next):
    """Inject distributed trace context into every enqueued job."""
    request.meta = request.meta or {}
    request.meta["trace_id"] = f"trace_{uuid.uuid4().hex[:16]}"
    request.meta["enqueued_by"] = "my-service"
    request.meta["enqueued_at_ms"] = int(time.time() * 1000)
    return await next(request)


@client.enqueue_middleware
async def enqueue_logging_middleware(request, next):
    """Log every enqueue operation with timing."""
    logging.info("[enqueue] Submitting %s to queue '%s'", request.type, request.queue)
    start = time.monotonic()
    result = await next(request)
    elapsed = time.monotonic() - start
    if result:
        logging.info(
            "[enqueue] Created %s as %s in %.3fs",
            request.type,
            result.id,
            elapsed,
        )
    else:
        logging.warning("[enqueue] Job %s was dropped by middleware", request.type)
    return result


# ---- Worker-side execution middleware ----

worker = ojs.Worker(
    "http://localhost:8080",
    queues=["email", "default"],
    concurrency=10,
)


@worker.middleware
async def logging_middleware(ctx: ojs.JobContext, next):
    """Log job start, completion, and failure with duration.

    Outermost middleware — wraps the entire execution chain.
    """
    logging.info(
        "[worker] Starting %s (id=%s, attempt=%d)",
        ctx.job_type,
        ctx.job_id,
        ctx.attempt,
    )
    start = time.monotonic()
    try:
        result = await next()
        elapsed = time.monotonic() - start
        logging.info(
            "[worker] Completed %s in %.3fs",
            ctx.job_type,
            elapsed,
        )
        return result
    except Exception:
        elapsed = time.monotonic() - start
        logging.error(
            "[worker] Failed %s after %.3fs",
            ctx.job_type,
            elapsed,
        )
        raise


@worker.middleware
async def metrics_middleware(ctx: ojs.JobContext, next):
    """Record success/failure metrics with duration.

    In production, emit to Prometheus, Datadog, or StatsD.
    """
    start = time.monotonic()
    try:
        result = await next()
        duration_ms = (time.monotonic() - start) * 1000
        logging.info(
            "[metrics] ojs.jobs.completed type=%s queue=%s duration=%.1fms",
            ctx.job_type,
            ctx.queue,
            duration_ms,
        )
        return result
    except Exception:
        duration_ms = (time.monotonic() - start) * 1000
        logging.info(
            "[metrics] ojs.jobs.failed type=%s queue=%s duration=%.1fms",
            ctx.job_type,
            ctx.queue,
            duration_ms,
        )
        raise


@worker.middleware
async def trace_restore_middleware(ctx: ojs.JobContext, next):
    """Restore distributed trace context from job metadata.

    Innermost middleware — closest to the handler.
    """
    trace_id = ctx.meta.get("trace_id")
    if trace_id:
        # In a real app, restore the OpenTelemetry span context here.
        logging.info("[trace] Restoring trace context: %s", trace_id)
    return await next()


# ---- Register handlers ----


@worker.register("email.send")
async def handle_email_send(ctx: ojs.JobContext):
    """Handle email.send jobs."""
    to = ctx.args[0]
    template = ctx.args[1] if len(ctx.args) > 1 else "default"
    logging.info("Sending email to %s (template=%s)", to, template)
    await asyncio.sleep(0.5)
    return {"sent": True, "to": to, "template": template}


@worker.register("notification.send")
async def handle_notification(ctx: ojs.JobContext):
    """Handle notification.send jobs."""
    user_id = ctx.args[0]
    message = ctx.args[1] if len(ctx.args) > 1 else ""
    logging.info("Sending notification to %s: %s", user_id, message)
    await asyncio.sleep(0.1)
    return {"notified": True, "user_id": user_id}


# ---- Main ----


async def main() -> None:
    # Enqueue a job (trace context and logging middleware will run).
    async with client:
        job = await client.enqueue(
            "email.send",
            ["user@example.com", "welcome"],
            queue="email",
        )
        logging.info("Job meta: %s", job.meta)

    # Start the worker (logging → metrics → tracing middleware chain).
    logging.info("Starting worker with middleware chain...")
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
