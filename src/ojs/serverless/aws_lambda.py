"""AWS Lambda adapter for SQS, HTTP push, and direct OJS invocations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any

from ojs.job import Job
from ojs.serverless.error_response import InvocationOutcome, failed_outcome
from ojs.serverless.handler_registry import HandlerRegistry, ServerlessHandler
from ojs.serverless.invocation_bridge import (
    InvocationBridge,
    create_completion_transport,
    run_sync_entrypoint,
)
from ojs.serverless.job_event_parser import (
    ServerlessEventError,
    decode_event,
    extract_job_event,
    parse_job_event,
)
from ojs.worker.completion_reporter import CompletionTransport

logger = logging.getLogger("ojs.serverless.lambda")


@dataclass(frozen=True)
class SQSBatchResponse:
    batchItemFailures: list[dict[str, str]] = field(  # noqa: N815 - AWS wire name
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return {"batchItemFailures": self.batchItemFailures}


@dataclass(frozen=True)
class PushDeliveryResponse:
    status: str
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return InvocationOutcome(
            status=self.status,
            result=self.result,
            error=self.error,
        ).to_dict(include_job_id=False)


@dataclass(frozen=True)
class DirectResponse:
    status: str
    job_id: str
    error: str | dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"status": self.status, "job_id": self.job_id}
        if self.error is not None:
            data["error"] = self.error
        return data


class LambdaHandler:
    """Register OJS handlers and expose Lambda-compatible entrypoints."""

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

    def sqs_handler(
        self,
        event: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any] | Coroutine[Any, Any, dict[str, Any]]:
        return run_sync_entrypoint(self.handle_sqs(event))

    async def handle_sqs(self, event: Mapping[str, Any]) -> dict[str, Any]:
        failures: list[dict[str, str]] = []
        records = event.get("Records", [])
        if not isinstance(records, list) or not records:
            self._logger.warning("SQS event contains no records")
            return SQSBatchResponse().to_dict()

        for record in records:
            message_id = "unknown"
            try:
                if not isinstance(record, Mapping):
                    raise ServerlessEventError("SQS record must be an object")
                raw_message_id = record.get("messageId", "unknown")
                if isinstance(raw_message_id, str):
                    message_id = raw_message_id
                body = decode_event(record.get("body", ""))
                job = extract_job_event(body)
                outcome = await self._bridge.invoke(job, report_completion=True)
                if outcome.requires_redelivery:
                    failures.append({"itemIdentifier": message_id})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(
                    "SQS invocation failed: message_id=%s error=%s",
                    message_id,
                    exc,
                )
                failures.append({"itemIdentifier": message_id})

        return SQSBatchResponse(batchItemFailures=failures).to_dict()

    def http_handler(
        self,
        event: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any] | Coroutine[Any, Any, dict[str, Any]]:
        return run_sync_entrypoint(self.handle_http(event))

    async def handle_http(self, event: Mapping[str, Any]) -> dict[str, Any]:
        method = _http_method(event)
        if method.upper() != "POST":
            return _http_response(405, {"error": "Method not allowed"})

        try:
            request_data = decode_event(event.get("body", ""))
            job = extract_job_event(request_data)
            outcome = await self._bridge.invoke(job, report_completion=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = failed_outcome("", exc)

        status_code = 400 if _is_invalid_request(outcome) else 200
        return _http_response(
            status_code,
            outcome.to_dict(include_job_id=False),
        )

    def direct_handler(
        self,
        event: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any] | Coroutine[Any, Any, dict[str, Any]]:
        return run_sync_entrypoint(self.handle_direct(event))

    async def handle_direct(self, event: Mapping[str, Any]) -> dict[str, Any]:
        try:
            job = extract_job_event(decode_event(event))
            outcome = await self._bridge.invoke(job, report_completion=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = failed_outcome(_job_id(event), exc)
        return outcome.to_dict()

    async def _handle_sqs_async(self, event: dict[str, Any]) -> dict[str, Any]:
        return await self.handle_sqs(event)

    async def _handle_http_async(self, event: dict[str, Any]) -> dict[str, Any]:
        return await self.handle_http(event)

    async def _handle_direct_async(self, event: dict[str, Any]) -> dict[str, Any]:
        return await self.handle_direct(event)

    async def _process_job(self, job: Job) -> Any:
        return await self._registry.execute(job)


def _http_method(event: Mapping[str, Any]) -> str:
    request_context = event.get("requestContext", {})
    if isinstance(request_context, Mapping):
        http = request_context.get("http", {})
        if isinstance(http, Mapping):
            method = http.get("method", "")
            if isinstance(method, str) and method:
                return method
    method = event.get("httpMethod", "")
    return method if isinstance(method, str) else ""


def _http_response(status_code: int, body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(dict(body)),
    }


def _is_invalid_request(outcome: InvocationOutcome) -> bool:
    return outcome.error is not None and outcome.error.get("code") == "invalid_request"


def _job_id(event: Mapping[str, Any]) -> str:
    value = event.get("id", "")
    return value if isinstance(value, str) else ""


_parse_job_event = parse_job_event
_run_async = run_sync_entrypoint

__all__ = [
    "DirectResponse",
    "LambdaHandler",
    "PushDeliveryResponse",
    "SQSBatchResponse",
    "_parse_job_event",
    "_run_async",
]
