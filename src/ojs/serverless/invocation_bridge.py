"""Execution and async-entrypoint bridge shared by serverless providers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from dataclasses import replace
from typing import Any, TypeVar

from ojs.job import Job
from ojs.serverless.error_response import (
    InvocationOutcome,
    callback_failed_outcome,
    completed_outcome,
    failed_outcome,
    validate_result,
)
from ojs.serverless.handler_registry import HandlerRegistry
from ojs.transport.http import HTTPTransport
from ojs.worker.completion_reporter import (
    Completed,
    CompletionReporter,
    CompletionTransport,
    Failed,
)

T = TypeVar("T")


class InvocationBridge:
    def __init__(
        self,
        registry: HandlerRegistry,
        completion_transport: CompletionTransport | None,
    ) -> None:
        self._registry = registry
        self._completion_transport = completion_transport

    async def invoke(
        self,
        job: Job,
        *,
        report_completion: bool,
    ) -> InvocationOutcome:
        try:
            result = await self._registry.execute(job)
            validate_result(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = failed_outcome(job.id, exc)
            if report_completion:
                if self._completion_transport is None:
                    return replace(outcome, requires_redelivery=True)
                try:
                    await self._report_failure(job, outcome)
                except asyncio.CancelledError:
                    raise
                except Exception as callback_error:
                    return callback_failed_outcome(job.id, callback_error)
            return outcome

        if report_completion and self._completion_transport is not None:
            try:
                await CompletionReporter(
                    self._completion_transport,
                    job.id,
                ).report(Completed(result))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return callback_failed_outcome(job.id, exc)
        return completed_outcome(job.id, result)

    async def _report_failure(
        self,
        job: Job,
        outcome: InvocationOutcome,
    ) -> None:
        if outcome.error is None or self._completion_transport is None:
            return
        await CompletionReporter(
            self._completion_transport,
            job.id,
        ).report(Failed(outcome.error))


def create_completion_transport(
    ojs_url: str | None,
    api_key: str | None,
    *,
    headers: Mapping[str, str] | None = None,
) -> CompletionTransport | None:
    """Build the HTTP transport used for ACK/NACK completion callbacks.

    ``api_key`` is sent as a standard ``Authorization: Bearer <api_key>``
    header, matching the OJS HTTP binding's authentication convention.
    Custom ``headers`` are additive: they are merged alongside the derived
    ``Authorization`` header rather than replacing it, unless the caller has
    already supplied their own ``Authorization`` header explicitly, in which
    case that explicit value is preserved.
    """
    if ojs_url is None:
        return None
    merged_headers: dict[str, str] = dict(headers) if headers else {}
    if api_key and not _has_header(merged_headers, "Authorization"):
        merged_headers["Authorization"] = f"Bearer {api_key}"
    return HTTPTransport(ojs_url, headers=merged_headers or None)


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    return any(key.lower() == name.lower() for key in headers)


def run_sync_entrypoint(
    coroutine: Coroutine[Any, Any, T],
) -> T | Coroutine[Any, Any, T]:
    """Run in a synchronous runtime, or return the awaitable to async callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    return coroutine


__all__ = [
    "InvocationBridge",
    "create_completion_transport",
    "run_sync_entrypoint",
]
