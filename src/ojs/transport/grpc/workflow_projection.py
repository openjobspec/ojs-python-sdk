"""Project HTTP workflow definitions into the canonical protobuf DAG."""

from __future__ import annotations

from typing import Any

from ojs.errors import OJSCapabilityError
from ojs.transport.grpc.enqueue_projection import project_enqueue
from ojs.workflow import WorkflowDefinition


def project_workflow(definition: WorkflowDefinition) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    defaults = definition.options or {}

    for source in definition.steps:
        if source.schema is not None:
            raise OJSCapabilityError(
                "The canonical OJS v1 gRPC WorkflowStep has no schema field. "
                "Use HTTP transport for schema-validated workflow steps."
            )
        source_options = source.options or {}
        if source_options.get("callback_type") is not None:
            raise OJSCapabilityError(
                "The canonical OJS v1 gRPC workflow DAG cannot represent "
                "conditional batch callbacks. Use HTTP transport for batch workflows."
            )

        body: dict[str, Any] = {
            "type": source.type,
            "args": source.args,
            "options": {**defaults, **source_options},
        }
        if source.meta is not None:
            body["meta"] = source.meta
        projected = project_enqueue(body)
        step: dict[str, Any] = {
            "id": source.id,
            "type": projected["type"],
            "args": projected["args"],
        }
        if source.depends_on:
            step["depends_on"] = source.depends_on
        if "options" in projected:
            step["options"] = projected["options"]
        steps.append(step)

    return {"name": definition.name, "steps": steps}


__all__ = ["project_workflow"]
