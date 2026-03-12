"""Tests for SSE subscription (ojs.subscribe)."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ojs.subscribe import SSEEvent, subscribe, subscribe_job, subscribe_queue


class FakeAsyncLineIterator:
    """Simulates httpx response.aiter_lines() from SSE data."""

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
    """Simulates httpx streaming response."""

    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def aiter_lines(self) -> FakeAsyncLineIterator:
        return FakeAsyncLineIterator(self._lines)

    async def __aenter__(self) -> FakeStreamResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class FakeAsyncClient:
    """Simulates httpx.AsyncClient with stream support."""

    def __init__(self, response: FakeStreamResponse) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None

    def stream(self, method: str, url: str, headers: dict[str, str] | None = None) -> FakeStreamResponse:
        self.last_url = url
        self.last_headers = headers
        return self._response

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.mark.asyncio
class TestSSESubscribe:
    async def test_parses_single_event(self) -> None:
        lines = [
            "event: job.completed",
            "id: evt-1",
            'data: {"job_id":"j1","state":"completed"}',
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "job:j1"):
                events.append(event)

        assert len(events) == 1
        assert events[0].type == "job.completed"
        assert events[0].id == "evt-1"
        assert events[0].data == {"job_id": "j1", "state": "completed"}

    async def test_parses_multiple_events(self) -> None:
        lines = [
            "event: job.active",
            'data: {"n":1}',
            "",
            "event: job.completed",
            'data: {"n":2}',
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "all"):
                events.append(event)

        assert len(events) == 2
        assert events[0].type == "job.active"
        assert events[1].type == "job.completed"

    async def test_default_message_type_when_no_event_field(self) -> None:
        lines = [
            'data: {"ping":true}',
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "all"):
                events.append(event)

        assert len(events) == 1
        assert events[0].type == "message"

    async def test_invalid_json_yields_raw(self) -> None:
        lines = [
            "data: not-valid-json",
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "all"):
                events.append(event)

        assert len(events) == 1
        assert events[0].data is None
        assert events[0].raw == "not-valid-json"

    async def test_empty_data_event_skipped(self) -> None:
        lines = [
            "event: heartbeat",
            "",
            "event: job.completed",
            'data: {"ok":true}',
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "all"):
                events.append(event)

        assert len(events) == 1
        assert events[0].type == "job.completed"

    async def test_auth_header_sent(self) -> None:
        response = FakeStreamResponse([])
        client = FakeAsyncClient(response)

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for _ in subscribe("http://localhost:8080", "all", auth="my-token"):
                pass

        assert client.last_headers is not None
        assert client.last_headers.get("Authorization") == "Bearer my-token"

    async def test_url_construction(self) -> None:
        response = FakeStreamResponse([])
        client = FakeAsyncClient(response)

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for _ in subscribe("http://localhost:8080/", "job:abc"):
                pass

        assert client.last_url is not None
        assert "channel=job:abc" in client.last_url
        assert client.last_url.startswith("http://localhost:8080/ojs/v1/events/stream")

    async def test_subscribe_job_constructs_channel(self) -> None:
        response = FakeStreamResponse([])
        client = FakeAsyncClient(response)

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for _ in subscribe_job("http://localhost:8080", "job-123"):
                pass

        assert client.last_url is not None
        assert "channel=job:job-123" in client.last_url

    async def test_subscribe_queue_constructs_channel(self) -> None:
        response = FakeStreamResponse([])
        client = FakeAsyncClient(response)

        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for _ in subscribe_queue("http://localhost:8080", "email"):
                pass

        assert client.last_url is not None
        assert "channel=queue:email" in client.last_url

    async def test_preserves_event_id(self) -> None:
        lines = [
            "id: 42",
            'data: {"x":1}',
            "",
        ]
        response = FakeStreamResponse(lines)
        client = FakeAsyncClient(response)

        events: list[SSEEvent] = []
        with patch("ojs.subscribe.httpx.AsyncClient", return_value=client):
            async for event in subscribe("http://localhost:8080", "all"):
                events.append(event)

        assert len(events) == 1
        assert events[0].id == "42"
