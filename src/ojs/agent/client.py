"""OJS Agent Client -- Agent Substrate Protocol operations.

Provides async methods for durable agent workflows: fork, merge,
pause/resume for human-in-the-loop, and deterministic replay.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

from ojs.agent.types import (
    AgentState,
    Divergence,
    ForkOptions,
    ForkResult,
    MergeOptions,
    MergeResult,
    MergeStrategy,
    ReplayOptions,
    ReplayResult,
    ResumeDecision,
)
from ojs.errors import OJSError

try:
    import httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    _HAS_HTTPX = False


class AgentClient:
    """Client for Agent Substrate Protocol operations.

    Usage::

        from ojs.agent import AgentClient

        agent = AgentClient(base_url="http://localhost:8080")

        # Fork an agent at turn 5
        result = await agent.fork("job-123", ForkOptions(at_turn=5, branch_name="alt"))

        # Pause for human approval
        await agent.pause("job-123", reason="high-cost tool call")

        # Resume with decision
        await agent.resume("job-123", ResumeDecision(approved=True, comment="ok"))
    """

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        transport: Any = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._transport = transport
        self._timeout = timeout
        self._client: Any = None

    async def fork(
        self,
        job_id: str,
        options: ForkOptions | None = None,
    ) -> ForkResult:
        """Fork an agent execution, creating a new conversation branch.

        Args:
            job_id: The job ID to fork from.
            options: Fork configuration (turn number, branch name).

        Returns:
            ForkResult with the new branch ID and content ID.
        """
        if not job_id:
            raise OJSError("agent: job_id required for fork")

        opts = options or ForkOptions()
        if opts.at_turn < 0:
            raise OJSError("agent: at_turn must be >= 0")
        body = {
            "at_turn": opts.at_turn,
            "branch_name": opts.branch_name,
        }
        data = await self._post(f"/v1/agents/{job_id}/fork", body)
        return ForkResult(
            branch_id=data.get("branch_id", ""),
            content_id=data.get("content_id", ""),
            parent_id=data.get("parent_id", ""),
        )

    async def merge(
        self,
        job_id: str,
        options: MergeOptions | None = None,
    ) -> MergeResult:
        """Merge two agent branches.

        Args:
            job_id: The job ID containing the branches.
            options: Merge configuration (branches, strategy).

        Returns:
            MergeResult with the merged content ID and any conflicts.
        """
        if not job_id:
            raise OJSError("agent: job_id required for merge")

        opts = options or MergeOptions()
        if not opts.branch_a:
            raise OJSError("agent: branch_a required for merge")
        if not opts.branch_b:
            raise OJSError("agent: branch_b required for merge")
        body = {
            "branch_a": opts.branch_a,
            "branch_b": opts.branch_b,
            "strategy": opts.strategy.value,
        }
        data = await self._post(f"/v1/agents/{job_id}/merge", body)
        return MergeResult(
            merged_id=data.get("merged_id", ""),
            conflicts=data.get("conflicts", []),
        )

    async def pause(self, job_id: str, reason: str = "") -> None:
        """Pause an agent for human-in-the-loop approval.

        Args:
            job_id: The job ID to pause.
            reason: Human-readable reason for the pause.
        """
        if not job_id:
            raise OJSError("agent: job_id required for pause")

        await self._post(f"/v1/agents/{job_id}/pause", {"reason": reason})

    async def resume(
        self,
        job_id: str,
        decision: ResumeDecision | None = None,
    ) -> None:
        """Resume a paused agent with a human decision.

        Args:
            job_id: The job ID to resume.
            decision: The human's approval/rejection and metadata.
        """
        if not job_id:
            raise OJSError("agent: job_id required for resume")

        dec = decision or ResumeDecision()
        body = {
            "approved": dec.approved,
            "comment": dec.comment,
            "metadata": dec.metadata,
        }
        await self._post(f"/v1/agents/{job_id}/resume", body)

    async def replay(
        self,
        job_id: str,
        options: ReplayOptions | None = None,
    ) -> ReplayResult:
        """Replay an agent execution from a checkpoint.

        Args:
            job_id: The job ID to replay.
            options: Replay configuration (start turn, mock providers).

        Returns:
            ReplayResult with step count and any divergences.
        """
        if not job_id:
            raise OJSError("agent: job_id required for replay")

        opts = options or ReplayOptions()
        body = {
            "from_turn": opts.from_turn,
            "mock_providers": opts.mock_providers,
        }
        data = await self._post(f"/v1/agents/{job_id}/replay", body)
        divergences = [
            Divergence(
                turn=d.get("turn", 0),
                expected=d.get("expected", ""),
                actual=d.get("actual", ""),
                reason=d.get("reason", ""),
            )
            for d in data.get("divergences", [])
        ]
        return ReplayResult(
            steps=data.get("steps", 0),
            divergences=divergences,
            deterministic=data.get("deterministic", len(divergences) == 0),
        )

    async def get_state(self, job_id: str) -> AgentState:
        """Get the current agent state.

        Args:
            job_id: The job ID.

        Returns:
            Current AgentState.
        """
        data = await self._get(f"/v1/agents/{job_id}/state")
        return AgentState(data.get("state", "running"))

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST to the agent API via httpx or injected transport."""
        if self._transport is not None:
            return await self._transport.post(self._base_url + path, body)
        return await self._http("POST", path, body)

    async def _get(self, path: str) -> dict[str, Any]:
        """GET from the agent API."""
        if self._transport is not None:
            return await self._transport.get(self._base_url + path)
        return await self._http("GET", path)

    async def _http(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Internal HTTP client using httpx."""
        if not _HAS_HTTPX:
            raise OJSError(
                "agent: httpx is required. Install with: pip install httpx"
            )
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Content-Type": "application/json", **self._headers},
            )
        url = self._base_url + path
        try:
            if method == "POST":
                resp = await self._client.post(url, json=body)
            else:
                resp = await self._client.get(url)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()
            except Exception:
                detail = {"error": exc.response.text}
            raise OJSError(
                f"agent: {method} {path} returned {exc.response.status_code}: "
                f"{detail.get('error', str(detail))}"
            ) from exc
        except httpx.RequestError as exc:
            raise OJSError(f"agent: {method} {path} failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AgentClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
