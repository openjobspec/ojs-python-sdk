"""Workflow example: chain, group, and batch.

Demonstrates composing multi-step job workflows.
"""

import asyncio
import logging

import ojs

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    async with ojs.Client("http://localhost:8080") as client:
        # Chain workflow: sequential execution
        wf = await client.workflow(
            ojs.chain(
                "onboarding-pipeline",
                [
                    ojs.JobRequest(
                        type="user.create_profile",
                        args=["user@example.com", {"plan": "free"}],
                    ),
                    ojs.JobRequest(
                        type="email.send",
                        args=["user@example.com", "welcome"],
                        queue="email",
                    ),
                    ojs.JobRequest(
                        type="analytics.track",
                        args=["user_signup", {"email": "user@example.com"}],
                    ),
                ],
            )
        )
        logger.info("Chain workflow created: %s (state: %s)", wf.id, wf.state)

        # Group workflow: parallel execution
        wf = await client.workflow(
            ojs.group(
                "image-resize",
                [
                    ojs.JobRequest(type="image.resize", args=["img.jpg", "thumbnail"]),
                    ojs.JobRequest(type="image.resize", args=["img.jpg", "medium"]),
                    ojs.JobRequest(type="image.resize", args=["img.jpg", "large"]),
                ],
            )
        )
        logger.info("Group workflow created: %s (state: %s)", wf.id, wf.state)

        # Batch workflow: parallel with callbacks
        wf = await client.workflow(
            ojs.batch(
                "data-import",
                [
                    ojs.JobRequest(type="import.chunk", args=[1, 1000]),
                    ojs.JobRequest(type="import.chunk", args=[1001, 2000]),
                    ojs.JobRequest(type="import.chunk", args=[2001, 3000]),
                ],
                on_complete=ojs.JobRequest(
                    type="import.finalize",
                    args=["cleanup_temp_files"],
                ),
                on_success=ojs.JobRequest(
                    type="email.send",
                    args=["admin@example.com", "import_complete"],
                    queue="email",
                ),
                on_failure=ojs.JobRequest(
                    type="email.send",
                    args=["admin@example.com", "import_failed"],
                    queue="email",
                ),
            )
        )
        logger.info("Batch workflow created: %s (state: %s)", wf.id, wf.state)

        # Check workflow status
        status = await client.get_workflow(wf.id)
        logger.info("Workflow %s: %s", status.id, status.state)
        for step in status.steps:
            logger.info("  Step %s (%s): %s", step.id, step.type, step.state)


if __name__ == "__main__":
    asyncio.run(main())
