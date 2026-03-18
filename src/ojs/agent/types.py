"""OJS Agent Substrate Protocol -- types and data classes.

Defines the core data structures for the Agent Substrate Protocol (ASP)
extension (ext_agent_v2). These types mirror the envelope extensions
specified in spec/spec/ojs-ai-agents-v2.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MergeStrategy(str, Enum):
    """Strategy for merging two conversation branches."""

    OURS = "ours"
    THEIRS = "theirs"
    UNION = "union"


class AgentState(str, Enum):
    """Agent execution lifecycle states."""

    RUNNING = "running"
    PAUSED_HUMAN = "paused_human"
    FORKED = "forked"
    MERGED = "merged"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ForkOptions:
    """Options for forking an agent execution."""

    at_turn: int = 0
    branch_name: str = ""


@dataclass(frozen=True)
class ForkResult:
    """Result of a fork operation."""

    branch_id: str = ""
    content_id: str = ""
    parent_id: str = ""


@dataclass(frozen=True)
class MergeOptions:
    """Options for merging two branches."""

    branch_a: str = ""
    branch_b: str = ""
    strategy: MergeStrategy = MergeStrategy.OURS


@dataclass(frozen=True)
class MergeResult:
    """Result of a merge operation."""

    merged_id: str = ""
    conflicts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResumeDecision:
    """Human decision to resume a paused agent."""

    approved: bool = True
    comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayOptions:
    """Options for replaying an agent execution."""

    from_turn: int = 0
    mock_providers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Divergence:
    """A point where replay diverged from the original execution."""

    turn: int = 0
    expected: str = ""
    actual: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ReplayResult:
    """Result of a replay operation."""

    steps: int = 0
    divergences: list[Divergence] = field(default_factory=list)
    deterministic: bool = True


@dataclass(frozen=True)
class ToolCall:
    """A standardized tool invocation record (MCP/A2A compatible)."""

    tool_id: str = ""
    tool_name: str = ""
    provider: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


@dataclass(frozen=True)
class MemoryNode:
    """A node in the content-addressed memory DAG."""

    content_id: str = ""
    parents: list[str] = field(default_factory=list)
    node_type: str = ""  # message, tool_call, tool_result, checkpoint
    payload: dict[str, Any] = field(default_factory=dict)
