"""OJS adapter for AWS Lambda.

Supports three invocation modes:

1. **SQS trigger** (recommended): Lambda receives batched SQS messages containing
   OJS job payloads. The adapter deserializes each message, dispatches to the
   registered handler, and returns partial batch failure responses so SQS only
   retries the failed messages.

2. **HTTP push delivery**: An OJS server POSTs job payloads to a Lambda Function
   URL. The adapter parses the push delivery request, processes the job, and
   returns an OJS-compatible response.

3. **Direct invocation**: A single OJS job event is passed directly to the
   Lambda function (e.g., via ``lambda.invoke()``).

Usage with SQS event source mapping::

    from ojs.serverless import LambdaHandler

    handler = LambdaHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        to, subject = ctx.args[0], ctx.args[1]
        await send_email(to, subject)

    # Wire up as the Lambda entry point
    lambda_handler = handler.sqs_handler

Usage with Lambda Function URL (push delivery)::

    from ojs.serverless import LambdaHandler

    handler = LambdaHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        await send_email(ctx.args[0])

    lambda_handler = handler.http_handler

Usage with direct invocation::

    from ojs.serverless import LambdaHandler

    handler = LambdaHandler()

    @handler.register("email.send")
    async def handle_email(ctx):
        await send_email(ctx.args[0])

    lambda_handler = handler.direct_handler
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from ojs.job import Job, JobContext, JobState

logger = logging.getLogger("ojs.serverless.lambda")

# Type alias for serverless handler functions.
# Handlers receive a JobContext and return an optional result value.
ServerlessHandler = Callable[[JobContext], Coroutine[Any, Any, Any]]


@dataclass(frozen=True)
class SQSBatchResponse:
    """Response format for SQS batch item failures.

    Returning failed message IDs tells SQS to retry only those messages.
    See: https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
    """

    batchItemFailures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"batchItemFailures": self.batchItemFailures}


@dataclass(frozen=True)
class PushDeliveryResponse:
    """Response body for OJS HTTP push delivery."""

    status: str
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status}
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d


@dataclass(frozen=True)
class DirectResponse:
    """Response for direct Lambda invocation."""

    status: str
    job_id: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status, "job_id": self.job_id}
        if self.error is not None:
            d["error"] = self.error
        return d


def _parse_job_event(data: dict[str, Any]) -> Job:
    """Parse a minimal job event dict into an OJS Job object.

    Serverless job events may not include all fields that a full
    server-returned Job would have. This function fills in defaults
    for missing fields.
    """
    return Job(
        id=data.get("id", ""),
        type=data.get("type", ""),
        state=JobState(data.get("state", "active")),
        args=data.get("args", []),
        queue=data.get("queue", "default"),
        meta=data.get("meta", {}),
        priority=data.get("priority", 0),
        attempt=data.get("attempt", 1),
        max_attempts=data.get("max_attempts", 3),
    )


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine, handling the case where an event loop
    may or may not already be running.

    In AWS Lambda, the runtime may or may not have a running event loop
    depending on the Python version and runtime configuration.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We are inside a running event loop (e.g., Lambda with async handler).
        # Create a new task and return the coroutine directly.
        # The caller is expected to await this in an async context.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class LambdaHandler:
    """OJS job handler adapter for AWS Lambda.

    Processes OJS jobs delivered via SQS event source mapping, HTTP push
    delivery (Lambda Function URL), or direct invocation.

    The handler supports registering multiple job type handlers, similar
    to the OJS Worker pattern but without the polling loop -- the Lambda
    runtime provides the invocation trigger instead.

    Args:
        ojs_url: Optional OJS server URL for callback operations (ack/nack).
            Required for HTTP push delivery mode; optional for SQS and direct.
        api_key: Optional API key for authenticating with the OJS server.
        logger_instance: Optional custom logger. Defaults to ``ojs.serverless.lambda``.
    """

    def __init__(
        self,
        ojs_url: str | None = None,
        *,
        api_key: str | None = None,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self._handlers: dict[str, ServerlessHandler] = {}
        self._ojs_url = ojs_url.rstrip("/") if ojs_url else None
        self._api_key = api_key
        self._logger = logger_instance or logger

    def register(self, job_type: str) -> Callable[[ServerlessHandler], ServerlessHandler]:
        """Register a handler for a job type (decorator form).

        Usage::

            @handler.register("email.send")
            async def handle_email(ctx: ojs.JobContext):
                to = ctx.args[0]
                await send_email(to)
        """

        def decorator(fn: ServerlessHandler) -> ServerlessHandler:
            self._handlers[job_type] = fn
            return fn

        return decorator

    def handler(self, job_type: str, fn: ServerlessHandler) -> None:
        """Register a handler for a job type (non-decorator form).

        Args:
            job_type: The OJS job type string (e.g., ``"email.send"``).
            fn: Async callable that receives a JobContext.
        """
        self._handlers[job_type] = fn

    # ------------------------------------------------------------------
    # SQS Event Source Mapping
    # ------------------------------------------------------------------

    def sqs_handler(self, event: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """AWS Lambda handler for SQS event source mapping.

        Processes a batch of SQS messages, each containing an OJS job
        payload in the message body. Returns partial batch failures so
        that SQS only retries the failed messages.

        Wire this as your Lambda entry point::

            lambda_handler = handler.sqs_handler

        Args:
            event: The SQS event from Lambda (contains ``Records``).
            context: The Lambda context object (unused but required by the runtime).

        Returns:
            A dict with ``batchItemFailures`` listing failed message IDs.
        """
        return _run_async(self._handle_sqs_async(event))

    async def _handle_sqs_async(self, event: dict[str, Any]) -> dict[str, Any]:
        """Async implementation of SQS batch processing."""
        failures: list[dict[str, str]] = []

        records = event.get("Records", [])
        if not records:
            self._logger.warning("SQS event contains no records")
            return SQSBatchResponse().to_dict()

        for record in records:
            message_id = record.get("messageId", "unknown")

            # Parse the job from the SQS message body
            try:
                body = record.get("body", "")
                if isinstance(body, str):
                    job_data = json.loads(body)
                else:
                    job_data = body
            except (json.JSONDecodeError, TypeError) as exc:
                self._logger.error(
                    "Failed to parse SQS message body: message_id=%s error=%s",
                    message_id,
                    exc,
                )
                failures.append({"itemIdentifier": message_id})
                continue

            # Process the job
            try:
                job = _parse_job_event(job_data)
                await self._process_job(job)
                self._logger.info(
                    "Job completed: job_id=%s job_type=%s",
                    job.id,
                    job.type,
                )
            except Exception as exc:
                self._logger.error(
                    "Job processing failed: message_id=%s error=%s",
                    message_id,
                    exc,
                )
                failures.append({"itemIdentifier": message_id})

        return SQSBatchResponse(batchItemFailures=failures).to_dict()

    # ------------------------------------------------------------------
    # HTTP Push Delivery (Lambda Function URL)
    # ------------------------------------------------------------------

    def http_handler(self, event: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """AWS Lambda handler for HTTP push delivery via Function URL or API Gateway.

        The OJS server POSTs job payloads to the Lambda Function URL. The
        request body follows the OJS push delivery format::

            {
                "job": { "id": "...", "type": "...", ... },
                "worker_id": "push_worker_...",
                "delivery_id": "del_..."
            }

        Args:
            event: The Lambda Function URL / API Gateway event.
            context: The Lambda context object.

        Returns:
            An API Gateway-compatible response dict with statusCode and body.
        """
        return _run_async(self._handle_http_async(event))

    async def _handle_http_async(self, event: dict[str, Any]) -> dict[str, Any]:
        """Async implementation of HTTP push delivery."""
        # Extract HTTP method
        method = (
            event.get("requestContext", {}).get("http", {}).get("method", "")
            or event.get("httpMethod", "")
        )

        if method.upper() != "POST":
            return {
                "statusCode": 405,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Method not allowed"}),
            }

        # Parse the request body
        try:
            body = event.get("body", "")
            if isinstance(body, str):
                request_data = json.loads(body)
            else:
                request_data = body
        except (json.JSONDecodeError, TypeError):
            resp = PushDeliveryResponse(
                status="failed",
                error={
                    "code": "invalid_request",
                    "message": "Failed to decode request body",
                    "retryable": False,
                },
            )
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(resp.to_dict()),
            }

        # Extract the job from the push delivery envelope
        job_data = request_data.get("job", request_data)
        job = _parse_job_event(job_data)

        try:
            result = await self._process_job(job)
            resp = PushDeliveryResponse(status="completed", result=result)
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(resp.to_dict()),
            }
        except Exception as exc:
            self._logger.error(
                "Job processing failed: job_id=%s error=%s",
                job.id,
                exc,
            )
            resp = PushDeliveryResponse(
                status="failed",
                error={
                    "code": "handler_error",
                    "message": str(exc),
                    "retryable": True,
                },
            )
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(resp.to_dict()),
            }

    # ------------------------------------------------------------------
    # Direct Invocation
    # ------------------------------------------------------------------

    def direct_handler(self, event: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """AWS Lambda handler for direct invocation with a single job event.

        The event is the OJS job payload itself::

            {
                "id": "...",
                "type": "email.send",
                "queue": "default",
                "args": [{"to": "user@example.com"}],
                "attempt": 1
            }

        Args:
            event: The OJS job event dict.
            context: The Lambda context object.

        Returns:
            A dict with ``status`` ("completed" or "failed"), ``job_id``, and
            optionally ``error``.
        """
        return _run_async(self._handle_direct_async(event))

    async def _handle_direct_async(self, event: dict[str, Any]) -> dict[str, Any]:
        """Async implementation of direct invocation."""
        job = _parse_job_event(event)

        try:
            await self._process_job(job)
            self._logger.info(
                "Job completed: job_id=%s job_type=%s",
                job.id,
                job.type,
            )
            return DirectResponse(status="completed", job_id=job.id).to_dict()
        except Exception as exc:
            self._logger.error(
                "Job processing failed: job_id=%s job_type=%s error=%s",
                job.id,
                job.type,
                exc,
            )
            return DirectResponse(
                status="failed",
                job_id=job.id,
                error=str(exc),
            ).to_dict()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _process_job(self, job: Job) -> Any:
        """Dispatch a job to the registered handler.

        Args:
            job: The parsed OJS Job.

        Returns:
            The handler's return value (may be None).

        Raises:
            RuntimeError: If no handler is registered for the job type.
            Exception: Any exception raised by the handler is propagated.
        """
        handler = self._handlers.get(job.type)
        if handler is None:
            raise RuntimeError(f"No handler registered for job type: {job.type}")

        ctx = JobContext(job=job, attempt=job.attempt or 1)
        return await handler(ctx)
