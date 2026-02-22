"""Server-Sent Events (SSE) subscription for real-time OJS job events.

Example::

    from ojs.subscribe import subscribe, subscribe_job

    async for event in subscribe_job("http://localhost:8080", "job-123"):
        print(f"State changed: {event['data']}")
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


@dataclass
class SSEEvent:
    """A single Server-Sent Event from the OJS stream."""

    id: str = ""
    type: str = "message"
    data: dict[str, Any] | None = None
    raw: str = ""


async def subscribe(
    url: str,
    channel: str,
    *,
    auth: str | None = None,
    timeout: float = 0,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to an SSE stream from the OJS server.

    Yields SSEEvent objects as they arrive. The connection stays open until
    the caller breaks out of the async for loop or the server closes it.

    Args:
        url: Base URL of the OJS server.
        channel: SSE channel (e.g., 'job:<id>', 'queue:<name>').
        auth: Bearer auth token (optional).
        timeout: Connection timeout in seconds (0 = no timeout).
    """
    stream_url = f"{url.rstrip('/')}/ojs/v1/events/stream?channel={channel}"
    headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"

    async with httpx.AsyncClient(timeout=timeout or None) as client:
        async with client.stream("GET", stream_url, headers=headers) as response:
            response.raise_for_status()

            event_type = ""
            event_id = ""
            event_data = ""

            async for line in response.aiter_lines():
                if line == "":
                    # Empty line = event boundary
                    if event_data:
                        try:
                            parsed = json.loads(event_data)
                        except json.JSONDecodeError:
                            parsed = None

                        yield SSEEvent(
                            id=event_id,
                            type=event_type or "message",
                            data=parsed,
                            raw=event_data,
                        )
                    event_type = ""
                    event_id = ""
                    event_data = ""
                elif line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("id: "):
                    event_id = line[4:]
                elif line.startswith("data: "):
                    event_data = line[6:]


async def subscribe_job(
    url: str,
    job_id: str,
    *,
    auth: str | None = None,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to events for a specific job."""
    async for event in subscribe(url, f"job:{job_id}", auth=auth):
        yield event


async def subscribe_queue(
    url: str,
    queue: str,
    *,
    auth: str | None = None,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to events for all jobs in a queue."""
    async for event in subscribe(url, f"queue:{queue}", auth=auth):
        yield event
