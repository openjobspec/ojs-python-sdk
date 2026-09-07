"""Canonical projection from job requests to workflow steps."""

from __future__ import annotations

from copy import deepcopy

from ojs.job import JobRequest
from ojs.workflow.models import WorkflowStep


def project_workflow_step(
    step_id: str,
    request: JobRequest,
    *,
    depends_on: list[str],
    callback_type: str | None = None,
) -> WorkflowStep:
    """Project every canonical enqueue field without maintaining a second codec."""
    envelope = deepcopy(request.to_dict())
    options = envelope.get("options")
    if callback_type is not None:
        options = dict(options or {})
        options["callback_type"] = callback_type

    return WorkflowStep(
        id=step_id,
        type=envelope["type"],
        args=envelope["args"],
        depends_on=list(depends_on),
        options=options,
        meta=envelope.get("meta"),
        schema=envelope.get("schema"),
    )


__all__ = ["project_workflow_step"]
