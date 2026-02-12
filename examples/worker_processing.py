"""Worker job processing example.

Demonstrates setting up a worker with handlers and middleware.
"""

import asyncio
import logging
import time

import ojs

logging.basicConfig(level=logging.INFO)


worker = ojs.Worker(
    "http://localhost:8080",
    queues=["email", "default"],
    concurrency=10,
)


# Register execution middleware
@worker.middleware
async def timing_middleware(ctx: ojs.JobContext, next):
    """Measure and log job execution time."""
    start = time.monotonic()
    try:
        result = await next()
        elapsed = time.monotonic() - start
        logging.info(
            "Job %s (%s) completed in %.3fs",
            ctx.job_id,
            ctx.job_type,
            elapsed,
        )
        return result
    except Exception:
        elapsed = time.monotonic() - start
        logging.error(
            "Job %s (%s) failed after %.3fs",
            ctx.job_id,
            ctx.job_type,
            elapsed,
        )
        raise


@worker.middleware
async def metadata_middleware(ctx: ojs.JobContext, next):
    """Log trace IDs from job metadata."""
    trace_id = ctx.meta.get("trace_id")
    if trace_id:
        logging.info("Processing job %s with trace_id=%s", ctx.job_id, trace_id)
    return await next()


# Register job handlers
@worker.register("email.send")
async def handle_email_send(ctx: ojs.JobContext):
    """Handle email.send jobs."""
    to = ctx.args[0]
    template = ctx.args[1] if len(ctx.args) > 1 else "default"

    logging.info("Sending email to %s using template %s", to, template)

    # Simulate email sending
    await asyncio.sleep(0.5)

    return {"sent": True, "to": to, "template": template}


@worker.register("notification.send")
async def handle_notification(ctx: ojs.JobContext):
    """Handle notification.send jobs."""
    user_id = ctx.args[0]
    message = ctx.args[1] if len(ctx.args) > 1 else ""

    logging.info("Sending notification to user %s: %s", user_id, message)
    await asyncio.sleep(0.1)

    return {"notified": True, "user_id": user_id}


async def main() -> None:
    logging.info("Starting OJS worker...")
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
