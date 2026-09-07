from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

import ojs
from ojs.agent import AgentClient, ForkOptions, durable
from ojs.transport.http import HTTPTransport


class RecordingRequestTransport:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {}
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.requests.append((method, path, body))
        return self.response


class LegacyAgentTransport:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((url, body))
        return {"branch_id": "branch-1"}

    async def get(self, url: str) -> dict[str, Any]:
        return {"state": "running"}


class TestAgentEndpoints:
    async def test_reserved_job_id_characters_are_quoted(self) -> None:
        transport = RecordingRequestTransport({"branch_id": "branch-1"})
        client = AgentClient("https://ojs.example.com", transport=transport)

        result = await client.fork("job/with ?reserved#chars", ForkOptions(at_turn=3))

        assert result.branch_id == "branch-1"
        assert transport.requests == [
            (
                "POST",
                "/agents/job%2Fwith%20%3Freserved%23chars/fork",
                {"at_turn": 3, "branch_name": ""},
            )
        ]

    async def test_legacy_transport_uses_canonical_prefix(self) -> None:
        transport = LegacyAgentTransport()
        client = AgentClient("https://ojs.example.com/", transport=transport)

        await client.fork("job-1")

        assert transport.posts[0][0] == ("https://ojs.example.com/ojs/v1/agents/job-1/fork")

    async def test_empty_state_job_id_is_rejected(self) -> None:
        client = AgentClient(
            "https://ojs.example.com",
            transport=RecordingRequestTransport(),
        )

        with pytest.raises(ojs.OJSValidationError):
            await client.get_state("")


class TestAgentHTTPPolicy:
    async def test_core_transport_uses_ojs_prefix(self) -> None:
        seen_paths: list[str] = []

        async def handle(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(
                200,
                json={"state": "running"},
                headers={"Content-Type": "application/openjobspec+json"},
            )

        http_client = httpx.AsyncClient(
            base_url="https://ojs.example.com",
            transport=httpx.MockTransport(handle),
        )
        transport = HTTPTransport(
            "https://ojs.example.com",
            client=http_client,
        )
        client = AgentClient("https://ignored.example.com", transport=transport)
        try:
            state = await client.get_state("job-1")
        finally:
            await http_client.aclose()

        assert state.value == "running"
        assert seen_paths == ["/ojs/v1/agents/job-1/state"]

    async def test_429_uses_canonical_error_mapping(self) -> None:
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
                headers={
                    "Content-Type": "application/openjobspec+json",
                    "Retry-After": "2",
                },
            )

        http_client = httpx.AsyncClient(
            base_url="https://ojs.example.com",
            transport=httpx.MockTransport(handle),
        )
        transport = HTTPTransport(
            "https://ojs.example.com",
            client=http_client,
            retry_config=ojs.RetryConfig(enabled=False),
        )
        client = AgentClient("https://ignored.example.com", transport=transport)
        try:
            with pytest.raises(ojs.RateLimitedError) as raised:
                await client.fork("job-1")
        finally:
            await http_client.aclose()

        assert raised.value.retry_after == 2

    async def test_cancellation_propagates_unchanged(self) -> None:
        started = asyncio.Event()

        class BlockingTransport(RecordingRequestTransport):
            async def request(
                self,
                method: str,
                path: str,
                *,
                body: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                started.set()
                await asyncio.Event().wait()
                return {}

        client = AgentClient(
            "https://ojs.example.com",
            transport=BlockingTransport(),
        )
        task = asyncio.create_task(client.pause("job-1"))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestDurableCompatibilityDecorator:
    async def test_warns_and_truthfully_marks_passthrough_semantics(self) -> None:
        calls: list[str] = []

        with pytest.warns(
            DeprecationWarning,
            match="does not provide checkpoint or replay semantics",
        ):

            @durable(policy={"retry": 3}, checkpoint_every=2)
            async def operation(value: str) -> str:
                calls.append(value)
                return value.upper()

        assert await operation("work") == "WORK"
        assert calls == ["work"]
        assert operation._ojs_durable is True
        assert operation._ojs_durable_semantics == "deprecated-passthrough"
        assert operation._ojs_policy == {"retry": 3}
        assert operation._ojs_checkpoint_every == 2

    @pytest.mark.parametrize("checkpoint_every", [0, -1, True, 1.5])
    def test_rejects_invalid_checkpoint_frequency(
        self,
        checkpoint_every: object,
    ) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            durable(checkpoint_every=checkpoint_every)  # type: ignore[arg-type]
