"""OJS Agent Substrate Protocol.

.. note::

   This module is part of **OJS Labs** — forward-looking R&D that is not
   part of the core release train. APIs may change between minor versions.
   See https://openjobspec.org/docs/moonshots/ for details.

Provides the AgentClient and supporting types for durable agent
workflows: fork/merge conversation branches, human-in-the-loop
pause/resume, and deterministic replay.

Usage::

    from ojs.agent import AgentClient, ForkOptions, ResumeDecision

    agent = AgentClient(base_url="http://localhost:8080")
    result = await agent.fork("job-123", ForkOptions(at_turn=5))
"""

from ojs.agent.client import AgentClient
from ojs.agent.types import (
    AgentState,
    Divergence,
    ForkOptions,
    ForkResult,
    MemoryNode,
    MergeOptions,
    MergeResult,
    MergeStrategy,
    ReplayOptions,
    ReplayResult,
    ResumeDecision,
    ToolCall,
)

__all__ = [
    "AgentClient",
    "AgentState",
    "Divergence",
    "ForkOptions",
    "ForkResult",
    "MemoryNode",
    "MergeOptions",
    "MergeResult",
    "MergeStrategy",
    "ReplayOptions",
    "ReplayResult",
    "ResumeDecision",
    "ToolCall",
]
