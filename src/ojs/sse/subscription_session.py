"""SSE client, stream, cancellation, and reconnection ownership."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast

import httpx

from ojs.errors import (
    OJSConnectionError,
    OJSError,
    OJSTimeoutError,
    map_error_response,
)
from ojs.sse.frame_parser import MalformedDataPolicy, SSEFrameParser
from ojs.sse.models import SSEEvent


class SSEResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]
    text: str

    def json(self) -> object: ...

    async def aread(self) -> bytes: ...

    def aiter_lines(self) -> AsyncIterator[str]: ...


class SSEClient(Protocol):
    def stream(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        headers: Mapping[str, str],
    ) -> AbstractAsyncContextManager[SSEResponse]: ...

    async def aclose(self) -> None: ...


class HttpxSSEClient:
    """Narrow adapter over httpx's broader streaming overloads."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    def stream(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        headers: Mapping[str, str],
    ) -> AbstractAsyncContextManager[SSEResponse]:
        return cast(
            AbstractAsyncContextManager[SSEResponse],
            self._client.stream(
                method,
                url,
                params=params,
                headers=headers,
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class _SSEStreamTerminatedError(Exception):
    """Internal signal: the server ended the stream permanently (HTTP 204).

    Per the SSE spec, a `204 No Content` response tells the client to stop
    reconnecting entirely — this is unconditional and overrides whatever
    ``reconnect``/``max_reconnects`` policy was configured, unlike a clean
    EOF (which reconnects if the policy allows) or a connection error
    (which reconnects only while attempts remain).
    """


class SubscriptionSession:
    """Own one client across initial and reconnect SSE streams."""

    def __init__(
        self,
        url: str,
        channel: str,
        *,
        auth: str | None = None,
        timeout: float = 0,
        client: SSEClient | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        malformed_data: MalformedDataPolicy = "raw",
        reconnect: bool = False,
        max_reconnects: int = 3,
        reconnect_delay: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not channel:
            raise ValueError("SSE channel must be non-empty")
        if max_reconnects < 0:
            raise ValueError("max_reconnects cannot be negative")
        if reconnect_delay < 0:
            raise ValueError("reconnect_delay cannot be negative")
        self._stream_url = f"{url.rstrip('/')}/ojs/v1/events/stream"
        self._channel = channel
        self._auth = auth
        self._malformed_data = malformed_data
        self._reconnect = reconnect
        self._max_reconnects = max_reconnects
        self._reconnect_delay = reconnect_delay
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or HttpxSSEClient(client_factory(timeout=timeout or None))

    async def events(self) -> AsyncIterator[SSEEvent]:
        reconnects = 0
        last_event_id = ""
        try:
            while True:
                try:
                    async for event in self._consume_once(last_event_id):
                        # Unconditional: per the SSE processing model the
                        # last event ID buffer is never reset between
                        # events, so an event's `id` already reflects
                        # either an explicit reset (empty string, which
                        # must clear our tracked value too) or inherited
                        # state (a non-empty sticky value). Guarding this
                        # with `if event.id:` would incorrectly keep a
                        # stale non-empty id after an explicit reset.
                        last_event_id = event.id
                        yield event
                except asyncio.CancelledError:
                    raise
                except _SSEStreamTerminatedError:
                    # HTTP 204 is a terminal signal: stop unconditionally,
                    # regardless of the configured reconnect policy.
                    return
                except (OJSConnectionError, OJSTimeoutError):
                    if not self._can_reconnect(reconnects):
                        raise
                else:
                    if not self._can_reconnect(reconnects):
                        return

                reconnects += 1
                await self._sleep(min(self._reconnect_delay * (2 ** (reconnects - 1)), 30.0))
        finally:
            if self._owns_client:
                await self._client.aclose()

    def _can_reconnect(self, reconnects: int) -> bool:
        return self._reconnect and reconnects < self._max_reconnects

    async def _consume_once(
        self,
        last_event_id: str,
    ) -> AsyncIterator[SSEEvent]:
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._auth:
            headers["Authorization"] = f"Bearer {self._auth}"
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id

        try:
            stream = self._client.stream(
                "GET",
                self._stream_url,
                params={"channel": self._channel},
                headers=headers,
            )
            async with stream as response:
                await self._raise_for_error(response)
                if response.status_code == 204:
                    # Per the SSE spec, "a client can be told to stop
                    # reconnecting using the HTTP 204 No Content response
                    # code." This is terminal: no frames are read (a 204
                    # response has no body to speak of) and no reconnect
                    # is attempted, regardless of the configured policy.
                    raise _SSEStreamTerminatedError()
                # Seed the buffer with the session's current sticky value
                # so a reconnected stream's first frame(s) — if they lack
                # their own `id` field — correctly inherit it rather than
                # starting from empty, matching the "last event ID buffer"
                # continuity a single long-lived connection would have.
                parser = SSEFrameParser(self._malformed_data, initial_event_id=last_event_id)
                async for line in response.aiter_lines():
                    event = parser.feed(line)
                    if event is not None:
                        yield event
                final_event = parser.finish()
                if final_event is not None:
                    yield final_event
        except asyncio.CancelledError:
            raise
        except OJSError:
            raise
        except httpx.TimeoutException as exc:
            raise OJSTimeoutError(f"SSE connection timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise OJSConnectionError(f"SSE connection failed: {exc}") from exc

    @staticmethod
    async def _raise_for_error(response: SSEResponse) -> None:
        if response.status_code < 400:
            return
        await response.aread()
        try:
            body = response.json()
        except (TypeError, ValueError):
            body = {
                "error": {
                    "code": "parse_error",
                    "message": response.text or "Unknown SSE error",
                    "retryable": response.status_code >= 500,
                }
            }
        if not isinstance(body, Mapping):
            body = {
                "error": {
                    "code": "parse_error",
                    "message": "SSE error response was not a JSON object",
                    "retryable": response.status_code >= 500,
                }
            }
        raise map_error_response(
            response.status_code,
            body,
            response.headers,
        )


__all__ = [
    "HttpxSSEClient",
    "SSEClient",
    "SSEResponse",
    "SubscriptionSession",
]
