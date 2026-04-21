"""Basic job enqueue example.

Demonstrates enqueuing jobs with the OJS Python SDK.
"""

import asyncio
import logging

import ojs

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    async with ojs.Client("http://localhost:8080") as client:
        # Simple enqueue
        job = await client.enqueue("email.send", ["user@example.com", "welcome"])
        logger.info("Enqueued job: %s (state: %s)", job.id, job.state.value)

        # Enqueue with options
        job = await client.enqueue(
            "email.send",
            [{"to": "user@example.com", "template": "onboarding"}],
            queue="email",
            retry=ojs.RetryPolicy(
                max_attempts=5,
                initial_interval="PT2S",
                backoff_coefficient=2.0,
            ),
            tags=["onboarding", "email"],
        )
        logger.info("Enqueued job with options: %s", job.id)

        # Enqueue with delay
        job = await client.enqueue(
            "notification.send",
            ["user_42", "Your trial ends tomorrow"],
            delay_until="2026-02-13T09:00:00Z",
        )
        logger.info("Enqueued delayed job: %s (state: %s)", job.id, job.state.value)

        # Batch enqueue
        jobs = await client.enqueue_batch(
            [
                ojs.JobRequest(
                    type="email.send",
                    args=["alice@example.com", "welcome"],
                    queue="email",
                ),
                ojs.JobRequest(
                    type="email.send",
                    args=["bob@example.com", "welcome"],
                    queue="email",
                ),
                ojs.JobRequest(
                    type="email.send",
                    args=["carol@example.com", "welcome"],
                    queue="email",
                ),
            ]
        )
        logger.info("Enqueued batch of %d jobs", len(jobs))

        # Check job status
        status = await client.get_job(job.id)
        logger.info("Job %s state: %s", status.id, status.state.value)


if __name__ == "__main__":
    asyncio.run(main())
