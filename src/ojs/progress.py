"""OJS Progress Reporting — report partial progress from long-running jobs.

Allows workers to send progress updates back to the OJS server
while a job is being processed.

Handler usage::

    @worker.register("data.import")
    async def handle_import(ctx):
        for i, row in enumerate(rows):
            await process_row(row)
            await ctx.report_progress(
                int(i / len(rows) * 100),
                message=f"Processed {i} rows",
            )

The standalone :func:`report_progress` helper remains available for code
that owns a transport directly.
"""

from __future__ import annotations

from typing import Any

from ojs.transport.base import Transport
from ojs.transport.capabilities import ProgressTransport


async def report_progress(
    transport: Transport,
    job_id: str,
    percentage: int,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    """Report progress for a job to the OJS server.

    Args:
        transport: The transport instance used to communicate with the server.
        job_id: The ID of the job reporting progress.
        percentage: Completion percentage (0-100).
        message: Optional human-readable progress message.
        data: Optional structured data with partial results.

    Raises:
        ValueError: If percentage is not between 0 and 100, or job_id is empty.
    """
    await _report_progress(transport, job_id, percentage, message, data)


async def _report_progress(
    transport: ProgressTransport,
    job_id: str,
    percentage: int,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    if not job_id:
        raise ValueError("job_id is required for progress reporting")
    if percentage < 0 or percentage > 100:
        raise ValueError(f"percentage must be between 0 and 100, got {percentage}")

    body: dict[str, Any] = {
        "job_id": job_id,
        "percentage": percentage,
    }
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data

    await transport.progress(body)
