"""OJS middleware types, chain management, and common implementations.

Provides core middleware type aliases and chain classes for both
enqueue middleware (client-side, linear chain) and execution middleware
(worker-side, nested/onion pattern).

Also provides ready-to-use middleware for logging, timeouts, retries,
and metrics.

Usage::

    from ojs.middleware import EnqueueMiddleware, ExecutionMiddleware
    from ojs.middleware.logging import logging_middleware
    from ojs.middleware.timeout import timeout_middleware
    from ojs.middleware.retry import retry_middleware
    from ojs.middleware.metrics import MetricsRecorder, metrics_middleware
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import Job, JobContext, JobRequest

# Enqueue middleware: receives a JobRequest and a next callable.
# Calling next(request) passes to the next middleware or the transport.
# Can modify the request, skip enqueue (return None), or replace it.
EnqueueNext = Callable[[JobRequest], Coroutine[Any, Any, Job | None]]
EnqueueMiddleware = Callable[[JobRequest, EnqueueNext], Coroutine[Any, Any, Job | None]]

# Execution middleware: receives a JobContext and a next callable.
# Calling next() passes to the next middleware or the handler.
ExecutionNext = Callable[[], Coroutine[Any, Any, Any]]
ExecutionMiddleware = Callable[[JobContext, ExecutionNext], Coroutine[Any, Any, Any]]


class EnqueueMiddlewareChain:
    """Manages the ordered list of enqueue middleware.

    Middleware runs in order: first added runs first (outermost).
    """

    def __init__(self) -> None:
        self._middlewares: list[EnqueueMiddleware] = []

    def add(self, middleware: EnqueueMiddleware) -> None:
        """Append middleware to the end of the chain."""
        self._middlewares.append(middleware)

    def prepend(self, middleware: EnqueueMiddleware) -> None:
        """Insert middleware at the beginning of the chain."""
        self._middlewares.insert(0, middleware)

    def insert_before(self, target: EnqueueMiddleware, middleware: EnqueueMiddleware) -> None:
        """Insert middleware before a specific existing middleware."""
        idx = self._middlewares.index(target)
        self._middlewares.insert(idx, middleware)

    def insert_after(self, target: EnqueueMiddleware, middleware: EnqueueMiddleware) -> None:
        """Insert middleware after a specific existing middleware."""
        idx = self._middlewares.index(target)
        self._middlewares.insert(idx + 1, middleware)

    def remove(self, middleware: EnqueueMiddleware) -> None:
        """Remove a middleware from the chain."""
        self._middlewares.remove(middleware)

    async def execute(self, request: JobRequest, final: EnqueueNext) -> Job | None:
        """Execute the middleware chain, ending with the final transport call."""

        async def _build_chain(middlewares: list[EnqueueMiddleware], req: JobRequest) -> Job | None:
            if not middlewares:
                return await final(req)

            current = middlewares[0]
            remaining = middlewares[1:]

            async def next_fn(r: JobRequest) -> Job | None:
                return await _build_chain(remaining, r)

            return await current(req, next_fn)

        return await _build_chain(list(self._middlewares), request)


class ExecutionMiddlewareChain:
    """Manages the ordered list of execution middleware.

    Uses the onion/nested pattern: first added is outermost.
    """

    def __init__(self) -> None:
        self._middlewares: list[ExecutionMiddleware] = []

    def add(self, middleware: ExecutionMiddleware) -> None:
        """Append middleware to the end of the chain."""
        self._middlewares.append(middleware)

    def prepend(self, middleware: ExecutionMiddleware) -> None:
        """Insert middleware at the beginning of the chain."""
        self._middlewares.insert(0, middleware)

    def insert_before(self, target: ExecutionMiddleware, middleware: ExecutionMiddleware) -> None:
        idx = self._middlewares.index(target)
        self._middlewares.insert(idx, middleware)

    def insert_after(self, target: ExecutionMiddleware, middleware: ExecutionMiddleware) -> None:
        idx = self._middlewares.index(target)
        self._middlewares.insert(idx + 1, middleware)

    def remove(self, middleware: ExecutionMiddleware) -> None:
        self._middlewares.remove(middleware)

    async def execute(
        self, ctx: JobContext, handler: Callable[[JobContext], Coroutine[Any, Any, Any]]
    ) -> Any:
        """Execute the middleware chain wrapping the handler."""

        async def _build_chain(
            middlewares: list[ExecutionMiddleware],
        ) -> Any:
            if not middlewares:
                return await handler(ctx)

            current = middlewares[0]
            remaining = middlewares[1:]

            async def next_fn() -> Any:
                return await _build_chain(remaining)

            return await current(ctx, next_fn)

        return await _build_chain(list(self._middlewares))


# --- Built-in middleware implementations ---

from ojs.middleware.logging import logging_middleware  # noqa: E402
from ojs.middleware.metrics import MetricsRecorder, metrics_middleware  # noqa: E402
from ojs.middleware.retry import retry_middleware  # noqa: E402
from ojs.middleware.timeout import TimeoutError as MiddlewareTimeoutError  # noqa: E402
from ojs.middleware.timeout import timeout_middleware  # noqa: E402

__all__ = [
    "EnqueueMiddleware",
    "EnqueueMiddlewareChain",
    "EnqueueNext",
    "ExecutionMiddleware",
    "ExecutionMiddlewareChain",
    "ExecutionNext",
    "MetricsRecorder",
    "MiddlewareTimeoutError",
    "logging_middleware",
    "metrics_middleware",
    "retry_middleware",
    "timeout_middleware",
]
