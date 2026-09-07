"""Consistent invocation outcomes across serverless providers and modes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ojs.serverless.handler_registry import HandlerNotFoundError
from ojs.serverless.job_event_parser import ServerlessEventError


@dataclass(frozen=True, slots=True)
class InvocationOutcome:
    status: str
    job_id: str = ""
    result: Any = None
    error: dict[str, Any] | None = None
    requires_redelivery: bool = False
    cause: BaseException | None = None
    """The original exception that produced this outcome, if any.

    Not serialized by :meth:`to_dict`. Retained so callers (such as the
    serverless adapters) can re-raise ``from cause`` and preserve the
    original traceback/context instead of surfacing a detached error.
    """

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"

    @property
    def retryable(self) -> bool:
        """Whether the underlying error is retryable per the OJS taxonomy.

        This reflects the *original* failure classification, independent of
        whether a completion callback (ACK/NACK) was itself delivered. Some
        callers use this instead of ``requires_redelivery`` when the platform
        redelivery decision should track the handler failure directly.
        """
        return self.error is not None and bool(self.error.get("retryable"))

    def to_dict(
        self,
        *,
        include_job_id: bool = True,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"status": self.status}
        if include_job_id:
            data["job_id"] = self.job_id
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = self.error
        return data


def completed_outcome(job_id: str, result: Any = None) -> InvocationOutcome:
    return InvocationOutcome(status="completed", job_id=job_id, result=result)


def failed_outcome(
    job_id: str,
    error: BaseException,
) -> InvocationOutcome:
    if isinstance(error, ServerlessEventError):
        code = "invalid_request"
        retryable = False
    elif isinstance(error, HandlerNotFoundError):
        code = "unknown_job_type"
        retryable = False
    elif isinstance(error, ResultSerializationError):
        code = "invalid_result"
        retryable = False
    else:
        code = "handler_error"
        retryable = True
    return InvocationOutcome(
        status="failed",
        job_id=job_id,
        error={
            "code": code,
            "message": type(error).__name__,
            "retryable": retryable,
        },
        cause=error,
    )


def callback_failed_outcome(job_id: str, error: BaseException) -> InvocationOutcome:
    return InvocationOutcome(
        status="failed",
        job_id=job_id,
        error={
            "code": "completion_callback_error",
            "message": type(error).__name__,
            "retryable": True,
        },
        requires_redelivery=True,
        cause=error,
    )


class ResultSerializationError(TypeError):
    """A serverless handler returned a value outside the JSON wire model."""


def validate_result(result: object) -> None:
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResultSerializationError("handler result is not JSON serializable") from exc


__all__ = [
    "InvocationOutcome",
    "ResultSerializationError",
    "callback_failed_outcome",
    "completed_outcome",
    "failed_outcome",
    "validate_result",
]
