"""OJS durable decorator for agent workflows.

The ``@durable`` decorator wraps a function so that its execution is
persisted as an OJS agent job. This enables fork, merge, replay, and
human-in-the-loop operations on arbitrary Python functions.

Usage::

    from ojs.agent import durable

    @durable(policy={"retry": 3, "timeout": 60})
    async def process_document(ctx, doc_url: str) -> str:
        content = await ctx.tool("fetch_url", url=doc_url)
        summary = await ctx.tool("summarize", text=content)
        return summary
"""

from __future__ import annotations

import functools
from typing import Any, Callable


def durable(
    *,
    policy: dict[str, Any] | None = None,
    checkpoint_every: int = 1,
) -> Callable:
    """Mark a function as a durable agent workflow.

    When a decorated function is called, OJS records each step into the
    memory DAG, enabling fork/merge/replay operations.

    Args:
        policy: Execution policy (retry count, timeout, etc.).
        checkpoint_every: Create a checkpoint every N steps.

    Returns:
        Decorator that wraps the function with durability semantics.
    """
    effective_policy = policy or {}

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # In the prototype, the decorator passes through to the
            # original function. The full implementation (P2) will:
            # 1. Create an OJS job envelope with ext_agent_v2
            # 2. Record each step in the memory DAG
            # 3. Support checkpoint/restore semantics
            #
            # The policy and checkpoint_every are stored as function
            # attributes for introspection by the OJS worker.
            return await fn(*args, **kwargs)

        wrapper._ojs_durable = True  # type: ignore[attr-defined]
        wrapper._ojs_policy = effective_policy  # type: ignore[attr-defined]
        wrapper._ojs_checkpoint_every = checkpoint_every  # type: ignore[attr-defined]
        return wrapper

    return decorator
