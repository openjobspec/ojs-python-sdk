"""OJS adapter for Azure Functions.

Supports two trigger modes:

1. **Queue trigger**: Azure Storage Queue or Service Bus Queue delivers messages
   containing OJS job payloads. The adapter deserializes the message, dispatches
   to the registered handler, and lets Azure handle retries via the poison queue.

2. **HTTP trigger**: An OJS server POSTs job payloads to an Azure Function HTTP
   endpoint. The adapter parses the push delivery request, processes the job,
   and returns an OJS-compatible response.

Usage with Azure Queue trigger::

    import azure.functions as func
    from ojs.serverless import AzureFunctionsHandler

    handler = AzureFunctionsHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        to = ctx.args[0]
        await send_email(to)

    async def main(msg: func.QueueMessage) -> None:
        await handler.handle_queue_message(msg.get_body().decode("utf-8"))

Usage with Azure HTTP trigger::

    import azure.functions as func
    from ojs.serverless import AzureFunctionsHandler

    handler = AzureFunctionsHandler(ojs_url="https://ojs.example.com")

    @handler.register("email.send")
    async def handle_email(ctx):
        to = ctx.args[0]
        await send_email(to)

    async def main(req: func.HttpRequest) -> func.HttpResponse:
        return await handler.handle_http_request(req)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from ojs.job import Job, JobContext, JobState

logger = logging.getLogger("ojs.serverless.azure")

# Type alias for serverless handler functions.
ServerlessHandler = Callable[[JobContext], Coroutine[Any, Any, Any]]


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


class AzureFunctionsHandler:
    """OJS job handler adapter for Azure Functions.

    Processes OJS jobs delivered via Azure Storage Queue, Service Bus Queue,
    or HTTP trigger. Supports registering multiple job type handlers using
    the same pattern as the OJS Worker.

    Args:
        ojs_url: Optional OJS server URL for callback operations.
        api_key: Optional API key for authenticating with the OJS server.
        logger_instance: Optional custom logger. Defaults to ``ojs.serverless.azure``.
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
    # Queue Trigger (Azure Storage Queue / Service Bus)
    # ------------------------------------------------------------------

    async def handle_queue_message(self, message_body: str | bytes | dict[str, Any]) -> Any:
        """Process a single queue message containing an OJS job.

        This method is intended to be called from an Azure Queue-triggered
        function. If the handler raises an exception, Azure will automatically
        move the message to the poison queue after the configured retry count.

        Args:
            message_body: The queue message body as a string (JSON), bytes, or
                already-parsed dict.

        Returns:
            The handler's return value (may be None).

        Raises:
            RuntimeError: If no handler is registered for the job type.
            json.JSONDecodeError: If the message body is not valid JSON.
            Exception: Any exception raised by the handler is propagated,
                allowing Azure to handle the retry/poison-queue logic.
        """
        # Parse the message body
        if isinstance(message_body, bytes):
            message_body = message_body.decode("utf-8")

        if isinstance(message_body, str):
            job_data = json.loads(message_body)
        else:
            job_data = message_body

        job = _parse_job_event(job_data)

        self._logger.info(
            "Processing queue message: job_id=%s job_type=%s",
            job.id,
            job.type,
        )

        result = await self._process_job(job)

        self._logger.info(
            "Job completed: job_id=%s job_type=%s",
            job.id,
            job.type,
        )

        return result

    # ------------------------------------------------------------------
    # HTTP Trigger
    # ------------------------------------------------------------------

    async def handle_http_request(self, req: Any) -> Any:
        """Process an HTTP request containing an OJS push delivery payload.

        This method is intended to be called from an Azure HTTP-triggered
        function. It accepts an ``azure.functions.HttpRequest`` and returns
        an ``azure.functions.HttpResponse``.

        The request body follows the OJS push delivery format::

            {
                "job": { "id": "...", "type": "...", ... },
                "worker_id": "push_worker_...",
                "delivery_id": "del_..."
            }

        Args:
            req: An ``azure.functions.HttpRequest`` object.

        Returns:
            An ``azure.functions.HttpResponse`` with the OJS push delivery response.

        Note:
            This method imports ``azure.functions`` lazily to avoid requiring
            the Azure Functions SDK as a hard dependency.
        """
        try:
            import azure.functions as func
        except ImportError:
            raise ImportError(
                "azure-functions package is required for HTTP trigger support. "
                "Install it with: pip install azure-functions"
            )

        # Validate HTTP method
        if req.method and req.method.upper() != "POST":
            return func.HttpResponse(
                body=json.dumps({"error": "Method not allowed"}),
                status_code=405,
                mimetype="application/json",
            )

        # Parse the request body
        try:
            body = req.get_json()
        except (ValueError, TypeError):
            return func.HttpResponse(
                body=json.dumps({
                    "status": "failed",
                    "error": {
                        "code": "invalid_request",
                        "message": "Failed to decode request body",
                        "retryable": False,
                    },
                }),
                status_code=400,
                mimetype="application/json",
            )

        # Extract the job from the push delivery envelope
        job_data = body.get("job", body)
        job = _parse_job_event(job_data)

        try:
            result = await self._process_job(job)
            response_body = {"status": "completed"}
            if result is not None:
                response_body["result"] = result
            return func.HttpResponse(
                body=json.dumps(response_body),
                status_code=200,
                mimetype="application/json",
            )
        except Exception as exc:
            self._logger.error(
                "Job processing failed: job_id=%s error=%s",
                job.id,
                exc,
            )
            return func.HttpResponse(
                body=json.dumps({
                    "status": "failed",
                    "error": {
                        "code": "handler_error",
                        "message": str(exc),
                        "retryable": True,
                    },
                }),
                status_code=200,
                mimetype="application/json",
            )

    # ------------------------------------------------------------------
    # Direct Processing (for timer triggers or other custom triggers)
    # ------------------------------------------------------------------

    async def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process a raw OJS job event dict.

        This is a generic entry point that can be used with any Azure
        trigger type where you have access to the raw job data.

        Args:
            event: The OJS job event as a dict.

        Returns:
            A dict with ``status`` ("completed" or "failed"), ``job_id``,
            and optionally ``error``.
        """
        job = _parse_job_event(event)

        try:
            await self._process_job(job)
            self._logger.info(
                "Job completed: job_id=%s job_type=%s",
                job.id,
                job.type,
            )
            return {"status": "completed", "job_id": job.id}
        except Exception as exc:
            self._logger.error(
                "Job processing failed: job_id=%s job_type=%s error=%s",
                job.id,
                job.type,
                exc,
            )
            return {"status": "failed", "job_id": job.id, "error": str(exc)}

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
