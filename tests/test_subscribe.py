"""Tests for SSE subscription actors and facade."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

import ojs
from ojs.sse import SSEDataError
from ojs.subscribe import SSEEvent, subscribe, subscribe_job, subscribe_queue


class FakeAsyncLineIterator:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._index = 0

    def __aiter__(self) -> FakeAsyncLineIterator:
        return self

    async def __anext__(self) -> str:
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line


class FakeStreamResponse:
    def __init__(
        self,
        lines: list[str],
        status_code: int = 200,
        *,
        json_body: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._lines = lines
        self._json_body = json_body
        self.status_code = status_code
        self.headers = headers or {}
        self.text = "" if json_body is None else json.dumps(json_body)
        self.exited = False

    def json(self) -> object:
        if self._json_body is None:
            raise ValueError("no JSON body")
        return self._json_body

    async def aread(self) -> bytes:
        return self.text.encode()

    def aiter_lines(self) -> AsyncIterator[str]:
        return FakeAsyncLineIterator(self._lines)

    async def __aenter__(self) -> FakeStreamResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.exited = True


class FakeAsyncClient:
    def __init__(
        self,
        response: FakeStreamResponse | list[FakeStreamResponse],
    ) -> None:
        self._responses = response if isinstance(response, list) else [response]
        self._index = 0
        self.last_url: str | None = None
        self.last_params: dict[str, str] | None = None
        self.last_headers: dict[str, str] | None = None
        self.stream_headers: list[dict[str, str]] = []
        self.closed = False

    def stream(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> FakeStreamResponse:
        self.last_url = url
        self.last_params = params
        self.last_headers = dict(headers)
        self.stream_headers.append(dict(headers))
        response = self._responses[self._index]
        self._index += 1
        return response

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
class TestSSESubscribe:
    async def test_parses_multiple_fields_and_events(self) -> None:
        """A block with no `id` field inherits the sticky last-event-id.

        Per the WHATWG SSE processing model, the last event ID buffer is
        never reset between dispatches: a later event without its own
        `id` field keeps whatever the buffer currently holds.
        """
        client = FakeAsyncClient(
            FakeStreamResponse(
                [
                    "event: job.active",
                    "id: evt-1",
                    'data: {"n":1}',
                    "",
                    'data: {"n":',
                    "data: 2}",
                    "",
                ]
            )
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "job:j1")]

        assert events == [
            SSEEvent(id="evt-1", type="job.active", data={"n": 1}, raw='{"n":1}'),
            SSEEvent(id="evt-1", type="message", data={"n": 2}, raw='{"n":\n2}'),
        ]
        assert client.closed

    async def test_explicit_empty_id_resets_sticky_buffer(self) -> None:
        """OJS-PY-050: an `id` field present but empty explicitly clears the buffer.

        This is distinct from a later event's `id` field being *absent*
        (which inherits the previous non-empty value, see
        ``test_parses_multiple_fields_and_events``): a bare ``id`` line (or
        ``id:`` with no value) resets the last event ID buffer to the empty
        string, matching the WHATWG worked example for this exact
        scenario.
        """
        client = FakeAsyncClient(
            FakeStreamResponse(
                [
                    "id: evt-1",
                    'data: {"n":1}',
                    "",
                    "id",
                    'data: {"n":2}',
                    "",
                    'data: {"n":3}',
                    "",
                ]
            )
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert [event.id for event in events] == ["evt-1", "", ""]

    async def test_explicit_empty_id_via_colon_resets_sticky_buffer(self) -> None:
        """`id:` (colon, no value) resets the buffer the same as bare `id`."""
        client = FakeAsyncClient(
            FakeStreamResponse(
                [
                    "id: evt-1",
                    'data: {"n":1}',
                    "",
                    "id:",
                    'data: {"n":2}',
                    "",
                ]
            )
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert [event.id for event in events] == ["evt-1", ""]

    async def test_eof_discards_unterminated_frame(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse(['data: {"ping":true}']))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert events == []

    async def test_invalid_json_yields_raw_by_default(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse(["data: not-valid-json", ""]))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert events[0].data is None
        assert events[0].raw == "not-valid-json"

    async def test_invalid_json_can_explicitly_raise(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse(["data: not-valid-json", ""]))

        with (
            patch("ojs.subscribe.httpx.AsyncClient", return_value=client),
            pytest.raises(SSEDataError),
        ):
            async for _ in subscribe(
                "http://localhost:8080",
                "all",
                malformed_data="raise",
            ):
                pass

    async def test_invalid_json_can_explicitly_yield_raw(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse(["data: not-valid-json", ""]))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    malformed_data="raw",
                )
            ]

        assert events[0].data is None
        assert events[0].raw == "not-valid-json"

    async def test_empty_data_event_is_skipped(self) -> None:
        client = FakeAsyncClient(
            FakeStreamResponse(
                [
                    "event: heartbeat",
                    "",
                    "event: job.completed",
                    'data: {"ok":true}',
                    "",
                ]
            )
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert [event.type for event in events] == ["job.completed"]

    async def test_auth_and_query_parameters_are_separate(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse([]))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for _ in subscribe(
                "http://localhost:8080/",
                "job:abc/with reserved?",
                auth="my-token",
            ):
                pass

        assert client.last_url == "http://localhost:8080/ojs/v1/events/stream"
        assert client.last_params == {"channel": "job:abc/with reserved?"}
        assert client.last_headers is not None
        assert client.last_headers["Authorization"] == "Bearer my-token"

    async def test_job_and_queue_facades_construct_channels(self) -> None:
        job_client = FakeAsyncClient(FakeStreamResponse([]))
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=job_client):
            async for _ in subscribe_job("http://localhost:8080", "job-123"):
                pass
        assert job_client.last_params == {"channel": "job:job-123"}

        queue_client = FakeAsyncClient(FakeStreamResponse([]))
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=queue_client):
            async for _ in subscribe_queue("http://localhost:8080", "email"):
                pass
        assert queue_client.last_params == {"channel": "queue:email"}

    async def test_channel_is_encoded_by_httpx(self) -> None:
        seen_query = ""

        async def handle(request: httpx.Request) -> httpx.Response:
            nonlocal seen_query
            seen_query = request.url.query.decode()
            return httpx.Response(
                200,
                content=b'data: {"ok":true}\n\n',
                headers={"Content-Type": "text/event-stream"},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        try:
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "job:id/with spaces?",
                    client=client,
                )
            ]
        finally:
            await client.aclose()

        assert events[0].data == {"ok": True}
        assert seen_query == "channel=job%3Aid%2Fwith+spaces%3F"

    async def test_http_errors_use_canonical_mapping(self) -> None:
        client = FakeAsyncClient(
            FakeStreamResponse(
                [],
                status_code=429,
                json_body={
                    "error": {
                        "code": "rate_limited",
                        "message": "slow down",
                        "retryable": True,
                    }
                },
                headers={"Retry-After": "3"},
            )
        )

        with (
            patch("ojs.subscribe.httpx.AsyncClient", return_value=client),
            pytest.raises(ojs.RateLimitedError) as raised,
        ):
            async for _ in subscribe("http://localhost:8080", "all"):
                pass

        assert raised.value.retry_after == 3

    async def test_unread_httpx_error_stream_uses_canonical_mapping(self) -> None:
        async def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={
                    "error": {
                        "code": "rate_limited",
                        "message": "slow down",
                        "retryable": True,
                    }
                },
                headers={"Retry-After": "2"},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        try:
            with pytest.raises(ojs.RateLimitedError) as raised:
                async for _ in subscribe(
                    "http://localhost:8080",
                    "all",
                    client=client,
                ):
                    pass
        finally:
            await client.aclose()

        assert raised.value.retry_after == 2

    async def test_http_204_ends_stream_without_reconnecting(self) -> None:
        """OJS-PY-051: HTTP 204 is a terminal signal, not a retryable EOF.

        Per the SSE spec, "a client can be told to stop reconnecting using
        the HTTP 204 No Content response code." Even with reconnection
        enabled and budget remaining, a 204 response must end the
        subscription for good.
        """
        client = FakeAsyncClient(FakeStreamResponse([], status_code=204))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=3,
                    reconnect_delay=0,
                )
            ]

        assert events == []
        # Only the single, terminal request was made — no reconnect attempt.
        assert len(client.stream_headers) == 1
        assert client.closed

    async def test_http_204_after_events_stops_without_reconnecting(self) -> None:
        """A 204 that arrives on a *reconnect* attempt is still terminal."""
        client = FakeAsyncClient(
            [
                FakeStreamResponse(["id: evt-1", 'data: {"n":1}', ""]),
                FakeStreamResponse([], status_code=204),
            ]
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=3,
                    reconnect_delay=0,
                )
            ]

        assert [event.id for event in events] == ["evt-1"]
        # The first stream ends cleanly (reconnect attempted per policy),
        # the second stream returns 204 and must not trigger a third
        # attempt even though reconnect budget remains.
        assert len(client.stream_headers) == 2
        assert client.closed

    async def test_http_204_without_reconnect_enabled_ends_cleanly(self) -> None:
        """204 behaves the same (cleanly terminal) even without `reconnect=True`."""
        client = FakeAsyncClient(FakeStreamResponse([], status_code=204))

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [event async for event in subscribe("http://localhost:8080", "all")]

        assert events == []
        assert len(client.stream_headers) == 1

    async def test_eof_reconnects_with_last_event_id(self) -> None:
        client = FakeAsyncClient(
            [
                FakeStreamResponse(["id: evt-1", 'data: {"n":1}', ""]),
                FakeStreamResponse(["id: evt-2", 'data: {"n":2}', ""]),
            ]
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=1,
                    reconnect_delay=0,
                )
            ]

        assert [event.id for event in events] == ["evt-1", "evt-2"]
        assert "Last-Event-ID" not in client.stream_headers[0]
        assert client.stream_headers[1]["Last-Event-ID"] == "evt-1"
        assert client.closed

    async def test_explicit_empty_id_clears_reconnect_header(self) -> None:
        """An explicit empty `id` clears the buffer so reconnect omits it.

        The first connection sets a non-empty id, then explicitly resets it
        to empty before the connection drops. The reconnect attempt must
        NOT resend the stale `evt-1` value as `Last-Event-ID`.
        """
        client = FakeAsyncClient(
            [
                FakeStreamResponse(
                    [
                        "id: evt-1",
                        'data: {"n":1}',
                        "",
                        "id",
                        'data: {"n":2}',
                        "",
                    ]
                ),
                FakeStreamResponse(['data: {"n":3}', ""]),
            ]
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=1,
                    reconnect_delay=0,
                )
            ]

        assert [event.id for event in events] == ["evt-1", "", ""]
        assert "Last-Event-ID" not in client.stream_headers[0]
        # The buffer was explicitly reset to empty by the second event's
        # bare `id` field, so the reconnect must NOT resend the earlier
        # (now stale) `evt-1` value.
        assert "Last-Event-ID" not in client.stream_headers[1]

    async def test_absent_id_field_reconnects_with_last_seen_value(self) -> None:
        """A block lacking an `id` field entirely does not clear the buffer.

        Contrasts with ``test_explicit_empty_id_clears_reconnect_header``:
        here the second event simply has no `id` field at all (rather than
        an explicit empty one), so the sticky value from the first event
        must still be sent as `Last-Event-ID` on reconnect.
        """
        client = FakeAsyncClient(
            [
                FakeStreamResponse(
                    [
                        "id: evt-1",
                        'data: {"n":1}',
                        "",
                        'data: {"n":2}',
                        "",
                    ]
                ),
                FakeStreamResponse(['data: {"n":3}', ""]),
            ]
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=1,
                    reconnect_delay=0,
                )
            ]

        assert [event.id for event in events] == ["evt-1", "evt-1", "evt-1"]
        assert client.stream_headers[1]["Last-Event-ID"] == "evt-1"

    async def test_timeout_reconnects_when_enabled(self) -> None:
        class TimingOutResponse(FakeStreamResponse):
            async def _timed_out_lines(self) -> AsyncIterator[str]:
                raise httpx.ReadTimeout("stream timed out")
                if False:
                    yield ""

            def aiter_lines(self) -> AsyncIterator[str]:
                return self._timed_out_lines()

        client = FakeAsyncClient(
            [
                TimingOutResponse([]),
                FakeStreamResponse(['data: {"reconnected":true}', ""]),
            ]
        )

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            events = [
                event
                async for event in subscribe(
                    "http://localhost:8080",
                    "all",
                    reconnect=True,
                    max_reconnects=1,
                    reconnect_delay=0,
                )
            ]

        assert events[0].data == {"reconnected": True}

    async def test_cancellation_closes_owned_stream_and_client(self) -> None:
        started = asyncio.Event()

        class BlockingResponse(FakeStreamResponse):
            async def _lines_forever(self) -> AsyncIterator[str]:
                started.set()
                await asyncio.Event().wait()
                if False:
                    yield ""

            def aiter_lines(self) -> AsyncIterator[str]:
                return self._lines_forever()

        response = BlockingResponse([])
        client = FakeAsyncClient(response)

        async def consume() -> None:
            with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
                async for _ in subscribe("http://localhost:8080", "all"):
                    pass

        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert response.exited
        assert client.closed

    async def test_injected_client_is_not_closed_by_subscription(self) -> None:
        client = FakeAsyncClient(FakeStreamResponse([]))

        async for _ in subscribe(
            "http://localhost:8080",
            "all",
            client=client,
        ):
            pass

        assert not client.closed


def test_subscribe_is_async_generator_function() -> None:
    assert inspect.isasyncgenfunction(subscribe)
