from __future__ import annotations

import inspect
import json
from typing import Any

import pytest

import ojs
from ojs.serverless import AzureFunctionsHandler, LambdaHandler


def _job_event(
    job_id: str,
    job_type: str,
    *,
    state: str = "active",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "type": job_type,
        "state": state,
        "args": ["payload"],
        "meta": {"trace_id": "trace-1"},
        "attempt": 2,
    }


class RecordingCompletionTransport:
    def __init__(self) -> None:
        self.acked: list[tuple[str, Any]] = []
        self.nacked: list[tuple[str, dict[str, Any]]] = []

    async def ack(self, job_id: str, result: Any = None) -> dict[str, Any]:
        self.acked.append((job_id, result))
        return {"acknowledged": True}

    async def nack(
        self,
        job_id: str,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        self.nacked.append((job_id, error))
        return {"state": "retryable"}


class FakeAzureRequest:
    def __init__(self, body: object, method: str = "POST") -> None:
        self._body = body
        self.method = method

    def get_json(self) -> object:
        return self._body


class RaisingJSONAzureRequest:
    """Fake Azure request whose ``get_json()`` mirrors a malformed HTTP body.

    The real ``azure.functions.HttpRequest.get_json()`` calls ``json.loads``
    internally and raises ``json.JSONDecodeError`` (a ``ValueError``
    subclass) for a malformed body, rather than going through this SDK's
    ``decode_event`` classification.
    """

    def __init__(self, method: str = "POST") -> None:
        self.method = method

    def get_json(self) -> object:
        return json.loads("{not-valid-json")


async def _run_as_queue_trigger(coro: Any) -> dict[str, Any]:
    """Simulate the Azure Functions host running a queue/Service Bus trigger.

    Raising abandons the message (redelivered per the queue's own
    max-delivery-count/dead-letter policy); returning normally completes it.
    Reports which happened, plus the raised exception when abandoned, so
    tests can assert both the redelivery decision and preserved error cause.
    """
    try:
        result = await coro
    except Exception as exc:
        return {"outcome": "abandoned", "error": exc}
    return {"outcome": "completed", "result": result}


async def _resolve_lambda_result(value: object) -> dict[str, Any]:
    assert inspect.isawaitable(value)
    result = await value
    assert isinstance(result, dict)
    return result


class TestLambdaHandler:
    async def test_sync_entrypoint_returns_awaitable_inside_running_loop(self) -> None:
        handler = LambdaHandler()

        @handler.register("task.ok")
        async def handle(ctx: ojs.JobContext) -> str:
            return "done"

        response = await _resolve_lambda_result(
            handler.direct_handler(_job_event("job-1", "task.ok"))
        )

        assert response == {
            "status": "completed",
            "job_id": "job-1",
            "result": "done",
        }

    async def test_invalid_state_is_a_normalized_boundary_error(self) -> None:
        handler = LambdaHandler()

        response = await handler.handle_direct(_job_event("job-1", "task.ok", state="not-a-state"))

        assert response["status"] == "failed"
        assert response["job_id"] == "job-1"
        assert response["error"] == {
            "code": "invalid_request",
            "message": "ServerlessEventError",
            "retryable": False,
        }

    async def test_http_malformed_event_returns_400(self) -> None:
        handler = LambdaHandler()

        response = await handler.handle_http(
            {
                "requestContext": {"http": {"method": "POST"}},
                "body": "[1, 2, 3]",
            }
        )

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "invalid_request"

    async def test_sqs_partial_failures_and_completion_callbacks(self) -> None:
        transport = RecordingCompletionTransport()
        handler = LambdaHandler(transport=transport)

        @handler.register("task.ok")
        async def handle_ok(ctx: ojs.JobContext) -> dict[str, bool]:
            return {"ok": True}

        @handler.register("task.fail")
        async def handle_fail(ctx: ojs.JobContext) -> None:
            raise ValueError("boom")

        response = await handler.handle_sqs(
            {
                "Records": [
                    {"messageId": "bad-json", "body": "{"},
                    {
                        "messageId": "failed-handler",
                        "body": json.dumps(_job_event("job-fail", "task.fail")),
                    },
                    {
                        "messageId": "completed",
                        "body": json.dumps(_job_event("job-ok", "task.ok")),
                    },
                ]
            }
        )

        assert response == {
            "batchItemFailures": [
                {"itemIdentifier": "bad-json"},
            ]
        }
        assert transport.acked == [("job-ok", {"ok": True})]
        assert transport.nacked[0][0] == "job-fail"
        assert transport.nacked[0][1]["code"] == "handler_error"

    async def test_sqs_redelivers_only_when_nack_delivery_fails(self) -> None:
        class FailingNackTransport(RecordingCompletionTransport):
            async def nack(
                self,
                job_id: str,
                error: dict[str, Any],
            ) -> dict[str, Any]:
                raise ConnectionError("callback unavailable")

        handler = LambdaHandler(transport=FailingNackTransport())

        @handler.register("task.fail")
        async def handle_fail(ctx: ojs.JobContext) -> None:
            raise ValueError("boom")

        response = await handler.handle_sqs(
            {
                "Records": [
                    {
                        "messageId": "failed-handler",
                        "body": json.dumps(_job_event("job-fail", "task.fail")),
                    }
                ]
            }
        )

        assert response == {"batchItemFailures": [{"itemIdentifier": "failed-handler"}]}

    async def test_non_json_result_is_nacked_without_escaping_boundary(self) -> None:
        transport = RecordingCompletionTransport()
        handler = LambdaHandler(transport=transport)

        @handler.register("task.bad-result")
        async def bad_result(ctx: ojs.JobContext) -> object:
            return object()

        response = await handler.handle_direct(_job_event("job-bad-result", "task.bad-result"))

        assert response["error"]["code"] == "invalid_result"
        assert response["error"]["retryable"] is False
        assert transport.nacked[0][0] == "job-bad-result"


class TestServerlessParity:
    async def test_handler_errors_match_across_modes_and_providers(self) -> None:
        lambda_handler = LambdaHandler()
        azure_handler = AzureFunctionsHandler()

        async def fail(ctx: ojs.JobContext) -> None:
            raise ValueError("private details")

        lambda_handler.handler("task.fail", fail)
        azure_handler.handler("task.fail", fail)
        event = _job_event("job-fail", "task.fail")

        direct = await lambda_handler.handle_direct(event)
        http = await lambda_handler.handle_http(
            {
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps({"job": event}),
            }
        )
        azure = await azure_handler.process_event(event)

        expected_error = {
            "code": "handler_error",
            "message": "ValueError",
            "retryable": True,
        }
        assert direct["error"] == expected_error
        assert json.loads(http["body"])["error"] == expected_error
        assert azure["error"] == expected_error

    async def test_azure_http_parsing_is_inside_error_boundary(self) -> None:
        handler = AzureFunctionsHandler()

        response = await handler.handle_http_request(
            FakeAzureRequest({"job": _job_event("job-1", "task", state="invalid")})
        )

        assert response.status_code == 400
        body = json.loads(response.get_body())
        assert body["error"]["code"] == "invalid_request"

    async def test_azure_http_malformed_json_is_invalid_request_before_handler_invocation(
        self,
    ) -> None:
        """OJS-PY-046: malformed JSON is invalid_request/400/non-retryable."""
        handler = AzureFunctionsHandler()
        handler_calls: list[str] = []

        @handler.register("task.ok")
        async def handle(ctx: ojs.JobContext) -> str:
            handler_calls.append(ctx.job.id)
            return "done"

        response = await handler.handle_http_request(RaisingJSONAzureRequest())

        assert response.status_code == 400
        body = json.loads(response.get_body())
        assert body["error"] == {
            "code": "invalid_request",
            "message": "ServerlessEventError",
            "retryable": False,
        }
        assert handler_calls == []

    async def test_azure_queue_uses_completion_callback(self) -> None:
        transport = RecordingCompletionTransport()
        handler = AzureFunctionsHandler(transport=transport)

        @handler.register("task.ok")
        async def handle(ctx: ojs.JobContext) -> str:
            return "done"

        result = await handler.handle_queue_message(json.dumps(_job_event("job-azure", "task.ok")))

        assert result == "done"
        assert transport.acked == [("job-azure", "done")]

    async def test_azure_queue_raises_after_retryable_nack_so_message_is_redelivered(
        self,
    ) -> None:
        """OJS-PY-045: a retryable handler failure must still abandon the message.

        Even though the NACK callback to the OJS backend succeeds, the
        Service Bus/Storage Queue trigger must raise so the Functions
        runtime abandons the message and it is redelivered; the original
        exception must remain attached as the cause.
        """
        transport = RecordingCompletionTransport()
        handler = AzureFunctionsHandler(transport=transport)
        original_error = ValueError("boom")

        @handler.register("task.fail")
        async def fail(ctx: ojs.JobContext) -> None:
            raise original_error

        host_result = await _run_as_queue_trigger(
            handler.handle_queue_message(json.dumps(_job_event("job-azure-fail", "task.fail")))
        )

        assert host_result["outcome"] == "abandoned"
        assert transport.nacked[0][0] == "job-azure-fail"
        assert transport.nacked[0][1]["code"] == "handler_error"
        raised = host_result["error"]
        assert isinstance(raised, RuntimeError)
        assert raised.__cause__ is original_error

    async def test_azure_queue_completes_after_non_retryable_outcome(self) -> None:
        """A non-retryable failure (unknown job type) completes the message.

        Retrying an unknown-job-type message forever would never succeed, so
        the message should be completed (not redelivered) once the NACK is
        recorded with the OJS backend.
        """
        transport = RecordingCompletionTransport()
        handler = AzureFunctionsHandler(transport=transport)

        host_result = await _run_as_queue_trigger(
            handler.handle_queue_message(json.dumps(_job_event("job-unknown", "task.missing")))
        )

        assert host_result["outcome"] == "completed"
        assert host_result["result"] is None
        assert transport.nacked[0][0] == "job-unknown"
        assert transport.nacked[0][1]["code"] == "unknown_job_type"
        assert transport.nacked[0][1]["retryable"] is False

    async def test_azure_queue_completes_on_malformed_body_without_reaching_handler(
        self,
    ) -> None:
        """A malformed queue message body never reaches a handler or NACK.

        The message is still non-retryable (it can never parse successfully)
        so the trigger completes it instead of retrying forever.
        """
        transport = RecordingCompletionTransport()
        handler = AzureFunctionsHandler(transport=transport)

        host_result = await _run_as_queue_trigger(handler.handle_queue_message("not-json-at-all"))

        assert host_result["outcome"] == "completed"
        assert host_result["result"] is None
        assert transport.acked == []
        assert transport.nacked == []

    async def test_azure_queue_raises_when_callback_delivery_itself_fails(self) -> None:
        """If the NACK callback cannot be delivered, always redeliver.

        The OJS backend never learned about the failure, so the platform
        must retry regardless of the original handler error's retryability.
        """

        class FailingNackTransport(RecordingCompletionTransport):
            async def nack(
                self,
                job_id: str,
                error: dict[str, Any],
            ) -> dict[str, Any]:
                raise ConnectionError("callback unavailable")

        handler = AzureFunctionsHandler(transport=FailingNackTransport())

        @handler.register("task.bad-result")
        async def bad_result(ctx: ojs.JobContext) -> object:
            return object()

        host_result = await _run_as_queue_trigger(
            handler.handle_queue_message(
                json.dumps(_job_event("job-bad-result", "task.bad-result"))
            )
        )

        assert host_result["outcome"] == "abandoned"
        raised = host_result["error"]
        assert isinstance(raised, RuntimeError)
        assert isinstance(raised.__cause__, ConnectionError)


def _patch_completion_http_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, str] | None]]:
    calls: list[tuple[str, dict[str, str] | None]] = []

    class StubTransport(RecordingCompletionTransport):
        pass

    def create_transport(
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> StubTransport:
        calls.append((url, headers))
        return StubTransport()

    monkeypatch.setattr(
        "ojs.serverless.invocation_bridge.HTTPTransport",
        create_transport,
    )
    return calls


def test_configured_url_and_api_key_create_callback_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_completion_http_transport(monkeypatch)

    LambdaHandler("https://ojs.example.com/", api_key="secret")
    AzureFunctionsHandler("https://ojs.example.com/", api_key="secret")

    assert calls == [
        ("https://ojs.example.com", {"Authorization": "Bearer secret"}),
        ("https://ojs.example.com", {"Authorization": "Bearer secret"}),
    ]


def test_api_key_never_sent_as_x_ojs_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OJS-PY-044 regression: the legacy X-OJS-API-Key-only header must not be sent."""
    calls = _patch_completion_http_transport(monkeypatch)

    LambdaHandler("https://ojs.example.com/", api_key="secret")

    assert len(calls) == 1
    _, headers = calls[0]
    assert headers is not None
    assert "X-OJS-API-Key" not in headers
    assert headers["Authorization"] == "Bearer secret"


def test_custom_headers_are_additive_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_completion_http_transport(monkeypatch)

    LambdaHandler(
        "https://ojs.example.com/",
        api_key="secret",
        headers={"X-Request-Source": "lambda-worker"},
    )

    assert calls == [
        (
            "https://ojs.example.com",
            {
                "X-Request-Source": "lambda-worker",
                "Authorization": "Bearer secret",
            },
        ),
    ]


def test_custom_headers_without_api_key_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_completion_http_transport(monkeypatch)

    AzureFunctionsHandler(
        "https://ojs.example.com/",
        headers={"X-Request-Source": "azure-worker"},
    )

    assert calls == [
        ("https://ojs.example.com", {"X-Request-Source": "azure-worker"}),
    ]


def test_explicit_authorization_header_is_not_overridden_by_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_completion_http_transport(monkeypatch)

    LambdaHandler(
        "https://ojs.example.com/",
        api_key="secret",
        headers={"Authorization": "Bearer explicit-token"},
    )

    assert calls == [
        ("https://ojs.example.com", {"Authorization": "Bearer explicit-token"}),
    ]


def test_no_api_key_and_no_headers_creates_transport_without_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_completion_http_transport(monkeypatch)

    LambdaHandler("https://ojs.example.com/")

    assert calls == [("https://ojs.example.com", None)]
