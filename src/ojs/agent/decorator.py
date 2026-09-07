"""Deprecated compatibility decorator for agent workflows.

The historical ``@durable`` decorator never persisted execution state.
Use :class:`ojs.durable.DurableContext` inside a worker handler for real
checkpoint and replay semantics.

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
import warnings
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class DurableFunction(Protocol[P, R_co]):
    _ojs_durable: bool
    _ojs_durable_semantics: str
    _ojs_policy: dict[str, Any]
    _ojs_checkpoint_every: int

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R_co]: ...


def durable(
    *,
    policy: dict[str, Any] | None = None,
    checkpoint_every: int = 1,
) -> Callable[[Callable[P, Awaitable[R_co]]], DurableFunction[P, R_co]]:
    """Return the deprecated pass-through durable compatibility marker.

    Args:
        policy: Execution policy (retry count, timeout, etc.).
        checkpoint_every: Create a checkpoint every N steps.

    Returns:
        A pass-through decorator retained for source compatibility.
    """
    if (
        not isinstance(checkpoint_every, int)
        or isinstance(checkpoint_every, bool)
        or checkpoint_every < 1
    ):
        raise ValueError("checkpoint_every must be a positive integer")
    effective_policy = dict(policy or {})
    warnings.warn(
        "ojs.agent.durable is deprecated because it does not provide checkpoint "
        "or replay semantics; use ojs.durable.DurableContext in a worker handler",
        DeprecationWarning,
        stacklevel=2,
    )

    def decorator(
        fn: Callable[P, Awaitable[R_co]],
    ) -> DurableFunction[P, R_co]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
            return await fn(*args, **kwargs)

        durable_wrapper = cast(DurableFunction[P, R_co], wrapper)
        durable_wrapper._ojs_durable = True
        durable_wrapper._ojs_durable_semantics = "deprecated-passthrough"
        durable_wrapper._ojs_policy = dict(effective_policy)
        durable_wrapper._ojs_checkpoint_every = checkpoint_every
        return durable_wrapper

    return decorator
