"""Azure Functions adapter for queue, HTTP, and direct OJS invocations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from ojs.job import Job
from ojs.serverless.error_response import InvocationOutcome, failed_outcome
from ojs.serverless.handler_registry import HandlerRegistry, ServerlessHandler
from ojs.serverless.invocation_bridge import (
    InvocationBridge,
    create_completion_transport,
)
from ojs.serverless.job_event_parser import (
    ServerlessEventError,
    decode_event,
    extract_job_event,
    parse_job_event,
)
from ojs.worker.completion_reporter import CompletionTransport

logger = logging.getLogger("ojs.serverless.azure")


class AzureFunctionsHandler:
    """Register OJS handlers and expose Azure-compatible entrypoints."""

    def __init__(
        self,
        ojs_url: str | None = None,
        *,
        api_key: str | None = None,
        headers: Mapping[str, str] | None = None,
        logger_instance: logging.Logger | None = None,
        transport: CompletionTransport | None = None,
    ) -> None:
        self._registry = HandlerRegistry()
        self._handlers = self._registry.handlers
        self._ojs_url = ojs_url.rstrip("/") if ojs_url else None
        self._api_key = api_key
        self._logger = logger_instance or logger
        completion_transport = transport or create_completion_transport(
            self._ojs_url,
            api_key,
            headers=headers,
        )
        self._bridge = InvocationBridge(self._registry, completion_transport)

    def register(
        self,
        job_type: str,
    ) -> Callable[[ServerlessHandler], ServerlessHandler]:
        return self._registry.register(job_type)

    def handler(self, job_type: str, fn: ServerlessHandler) -> None:
        self._registry.add(job_type, fn)

    async def handle_queue_message(
        self,
        message_body: str | bytes | dict[str, Any],
    ) -> Any:
        """Process a Storage Queue / Service Bus queue trigger message.

        Azure queue and Service Bus triggers use exception-based redelivery:
        raising abandons the message so the runtime redelivers it (subject to
        the queue's own max-delivery-count/dead-letter policy), while
        returning normally completes it. A *retryable* failure (per the OJS
        error taxonomy) must still raise even after the completion callback
        (ACK/NACK) to the OJS backend succeeds, so the message is redelivered
        for another attempt. A *non-retryable* failure (invalid request,
        unknown job type, unserializable result, or a failed-callback outcome
        that is not itself retryable) completes the message instead of
        retrying a poison message forever. The original exception is always
        preserved as the ``__cause__`` of any re-raised error.
        """
        try:
            job = extract_job_event(decode_event(message_body))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return _resolve_queue_trigger_outcome(failed_outcome("", exc))

        outcome = await self._bridge.invoke(job, report_completion=True)
        return _resolve_queue_trigger_outcome(outcome)

    async def handle_http_request(self, req: Any) -> Any:
        try:
            import azure.functions as func
        except ImportError as exc:
            raise ImportError(
                "azure-functions package is required for HTTP trigger support. "
                "Install it with: pip install azure-functions"
            ) from exc

        if req.method and req.method.upper() != "POST":
            return _azure_response(func, 405, {"error": "Method not allowed"})

        try:
            request_data = decode_event(_parse_http_request_json(req))
            job = extract_job_event(request_data)
            outcome = await self._bridge.invoke(job, report_completion=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = failed_outcome("", exc)

        status_code = 400 if _is_invalid_request(outcome) else 200
        return _azure_response(
            func,
            status_code,
            outcome.to_dict(include_job_id=False),
        )

    async def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            job = extract_job_event(decode_event(event))
            outcome = await self._bridge.invoke(job, report_completion=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = failed_outcome(_job_id(event), exc)
        return outcome.to_dict()

    async def _process_job(self, job: Job) -> Any:
        return await self._registry.execute(job)


def _azure_response(
    functions_module: Any,
    status_code: int,
    body: Mapping[str, Any],
) -> Any:
    return functions_module.HttpResponse(
        body=json.dumps(dict(body)),
        status_code=status_code,
        mimetype="application/json",
    )


def _is_invalid_request(outcome: InvocationOutcome) -> bool:
    return outcome.error is not None and outcome.error.get("code") == "invalid_request"


def _parse_http_request_json(req: Any) -> Any:
    """Parse an Azure HTTP request body as JSON before handler invocation.

    ``req.get_json()`` raises ``ValueError`` (``json.JSONDecodeError`` for
    malformed JSON, or ``UnicodeDecodeError`` for an undecodable body; both
    are ``ValueError`` subclasses) directly from the ``azure-functions``
    package, bypassing this SDK's own ``decode_event`` classification. That
    failure is normalized here into a ``ServerlessEventError`` so it is
    classified as ``invalid_request`` (HTTP 400, non-retryable) the same way
    a malformed string/bytes body already is, instead of surfacing as an
    opaque, retryable ``handler_error``.
    """
    try:
        return req.get_json()
    except ValueError as exc:
        raise ServerlessEventError("HTTP request body is not valid JSON") from exc


def _resolve_queue_trigger_outcome(outcome: InvocationOutcome) -> Any:
    """Translate an invocation outcome into queue-trigger redelivery signal.

    Raises (preserving ``outcome.cause`` as the exception context) when the
    failure is retryable, so the Functions runtime abandons the message and
    the queue/Service Bus redelivers it. Otherwise returns the outcome result
    normally so the runtime completes the message.
    """
    if outcome.retryable:
        raise RuntimeError(json.dumps(outcome.to_dict())) from outcome.cause
    return outcome.result


def _job_id(event: Mapping[str, Any]) -> str:
    value = event.get("id", "")
    return value if isinstance(value, str) else ""


_parse_job_event = parse_job_event

__all__ = ["AzureFunctionsHandler", "_parse_job_event"]
