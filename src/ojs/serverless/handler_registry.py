"""Shared handler registration and dispatch for serverless adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ojs.job import Job, JobContext

ServerlessHandler = Callable[[JobContext], Awaitable[Any]]


class HandlerNotFoundError(RuntimeError):
    """No serverless handler was registered for an incoming job type."""


class HandlerRegistry:
    def __init__(self) -> None:
        self.handlers: dict[str, ServerlessHandler] = {}

    def register(
        self,
        job_type: str,
    ) -> Callable[[ServerlessHandler], ServerlessHandler]:
        def decorator(handler: ServerlessHandler) -> ServerlessHandler:
            self.handlers[job_type] = handler
            return handler

        return decorator

    def add(self, job_type: str, handler: ServerlessHandler) -> None:
        self.handlers[job_type] = handler

    async def execute(self, job: Job) -> Any:
        handler = self.handlers.get(job.type)
        if handler is None:
            raise HandlerNotFoundError(f"No handler registered for job type: {job.type}")
        return await handler(JobContext(job=job, attempt=job.attempt or 1))


__all__ = ["HandlerNotFoundError", "HandlerRegistry", "ServerlessHandler"]
