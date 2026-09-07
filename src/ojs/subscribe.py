"""Server-Sent Events facade for real-time OJS job events."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from ojs.sse import MalformedDataPolicy, SSEClient, SSEEvent, SubscriptionSession


async def subscribe(
    url: str,
    channel: str,
    *,
    auth: str | None = None,
    timeout: float = 0,  # noqa: ASYNC109 - public connection-timeout API
    client: SSEClient | None = None,
    malformed_data: MalformedDataPolicy = "raw",
    reconnect: bool = False,
    max_reconnects: int = 3,
    reconnect_delay: float = 0.5,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to one encoded OJS SSE channel.

    Reconnection is explicit. Set ``reconnect=True`` to reconnect after EOF or
    connection loss and send ``Last-Event-ID`` for replay.
    """
    session = SubscriptionSession(
        url,
        channel,
        auth=auth,
        timeout=timeout,
        client=client,
        client_factory=httpx.AsyncClient,
        malformed_data=malformed_data,
        reconnect=reconnect,
        max_reconnects=max_reconnects,
        reconnect_delay=reconnect_delay,
    )
    async for event in session.events():
        yield event


async def subscribe_job(
    url: str,
    job_id: str,
    *,
    auth: str | None = None,
    timeout: float = 0,  # noqa: ASYNC109 - public connection-timeout API
    client: SSEClient | None = None,
    malformed_data: MalformedDataPolicy = "raw",
    reconnect: bool = False,
    max_reconnects: int = 3,
    reconnect_delay: float = 0.5,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to events for a specific job."""
    async for event in subscribe(
        url,
        f"job:{job_id}",
        auth=auth,
        timeout=timeout,
        client=client,
        malformed_data=malformed_data,
        reconnect=reconnect,
        max_reconnects=max_reconnects,
        reconnect_delay=reconnect_delay,
    ):
        yield event


async def subscribe_queue(
    url: str,
    queue: str,
    *,
    auth: str | None = None,
    timeout: float = 0,  # noqa: ASYNC109 - public connection-timeout API
    client: SSEClient | None = None,
    malformed_data: MalformedDataPolicy = "raw",
    reconnect: bool = False,
    max_reconnects: int = 3,
    reconnect_delay: float = 0.5,
) -> AsyncIterator[SSEEvent]:
    """Subscribe to events for all jobs in a queue."""
    async for event in subscribe(
        url,
        f"queue:{queue}",
        auth=auth,
        timeout=timeout,
        client=client,
        malformed_data=malformed_data,
        reconnect=reconnect,
        max_reconnects=max_reconnects,
        reconnect_delay=reconnect_delay,
    ):
        yield event


__all__ = ["SSEEvent", "subscribe", "subscribe_job", "subscribe_queue"]
