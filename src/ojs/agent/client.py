"""OJS Agent Client -- Agent Substrate Protocol operations.

Provides async methods for durable agent workflows: fork, merge,
pause/resume for human-in-the-loop, and deterministic replay.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ojs.agent.endpoints import agent_endpoint
from ojs.agent.types import (
    AgentState,
    Divergence,
    ForkOptions,
    ForkResult,
    MergeOptions,
    MergeResult,
    ReplayOptions,
    ReplayResult,
    ResumeDecision,
)
from ojs.errors import OJSValidationError
from ojs.transport.http import HTTPTransport


class AgentTransport(Protocol):
    """Compatibility protocol for the original injected agent transport."""

    async def post(self, url: str, body: dict[str, Any]) -> dict[str, Any]: ...

    async def get(self, url: str) -> dict[str, Any]: ...


@runtime_checkable
class AgentRequestTransport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class _LegacyAgentTransportAdapter:
    def __init__(self, base_url: str, transport: AgentTransport) -> None:
        self._base_url = base_url
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/ojs/v1{path}"
        if method == "POST":
            return await self._transport.post(url, body or {})
        if method == "GET":
            return await self._transport.get(url)
        raise OJSValidationError(f"agent: unsupported HTTP method {method!r}")


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
        transport: AgentRequestTransport | AgentTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owned_transport: HTTPTransport | None = None
        if transport is None:
            self._owned_transport = HTTPTransport(
                self._base_url,
                timeout=timeout,
                headers=headers,
            )
            self._transport: AgentRequestTransport = self._owned_transport
        elif isinstance(transport, AgentRequestTransport):
            self._transport = transport
        else:
            self._transport = _LegacyAgentTransportAdapter(
                self._base_url,
                transport,
            )

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
            raise OJSValidationError("agent: job_id required for fork")

        opts = options or ForkOptions()
        if opts.at_turn < 0:
            raise OJSValidationError("agent: at_turn must be >= 0")
        body = {
            "at_turn": opts.at_turn,
            "branch_name": opts.branch_name,
        }
        data = await self._post(agent_endpoint(job_id, "fork"), body)
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
            raise OJSValidationError("agent: job_id required for merge")

        opts = options or MergeOptions()
        if not opts.branch_a:
            raise OJSValidationError("agent: branch_a required for merge")
        if not opts.branch_b:
            raise OJSValidationError("agent: branch_b required for merge")
        body = {
            "branch_a": opts.branch_a,
            "branch_b": opts.branch_b,
            "strategy": opts.strategy.value,
        }
        data = await self._post(agent_endpoint(job_id, "merge"), body)
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
            raise OJSValidationError("agent: job_id required for pause")

        await self._post(agent_endpoint(job_id, "pause"), {"reason": reason})

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
            raise OJSValidationError("agent: job_id required for resume")

        dec = decision or ResumeDecision()
        body = {
            "approved": dec.approved,
            "comment": dec.comment,
            "metadata": dec.metadata,
        }
        await self._post(agent_endpoint(job_id, "resume"), body)

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
            raise OJSValidationError("agent: job_id required for replay")

        opts = options or ReplayOptions()
        body = {
            "from_turn": opts.from_turn,
            "mock_providers": opts.mock_providers,
        }
        data = await self._post(agent_endpoint(job_id, "replay"), body)
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
        if not job_id:
            raise OJSValidationError("agent: job_id required for state lookup")
        data = await self._get(agent_endpoint(job_id, "state"))
        return AgentState(data.get("state", "running"))

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._transport.request("POST", path, body=body)

    async def _get(self, path: str) -> dict[str, Any]:
        return await self._transport.request("GET", path)

    async def close(self) -> None:
        """Close only the core transport owned by this client."""
        if self._owned_transport is not None:
            await self._owned_transport.close()
            self._owned_transport = None

    async def __aenter__(self) -> AgentClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
