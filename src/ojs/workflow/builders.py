"""Workflow composition builders."""

from __future__ import annotations

from ojs.job import JobRequest
from ojs.workflow.models import WorkflowDefinition, WorkflowStep
from ojs.workflow.step_projection import project_workflow_step


def chain(
    name: str,
    jobs: list[JobRequest],
    *,
    options: dict[str, object] | None = None,
) -> WorkflowDefinition:
    """Build a sequential workflow."""
    steps = [
        project_workflow_step(
            f"step-{index}",
            job,
            depends_on=[f"step-{index - 1}"] if index > 0 else [],
        )
        for index, job in enumerate(jobs)
    ]
    return WorkflowDefinition(name=name, steps=steps, options=options)


def group(
    name: str,
    jobs: list[JobRequest],
    *,
    options: dict[str, object] | None = None,
) -> WorkflowDefinition:
    """Build a parallel workflow."""
    steps = [
        project_workflow_step(f"step-{index}", job, depends_on=[]) for index, job in enumerate(jobs)
    ]
    return WorkflowDefinition(name=name, steps=steps, options=options)


def batch(
    name: str,
    jobs: list[JobRequest],
    *,
    on_complete: JobRequest | None = None,
    on_success: JobRequest | None = None,
    on_failure: JobRequest | None = None,
    options: dict[str, object] | None = None,
) -> WorkflowDefinition:
    """Build a parallel workflow with conditional callback steps."""
    parallel_ids = [f"step-{index}" for index in range(len(jobs))]
    steps: list[WorkflowStep] = [
        project_workflow_step(step_id, job, depends_on=[])
        for step_id, job in zip(parallel_ids, jobs, strict=True)
    ]

    callbacks = (
        ("on_complete", on_complete),
        ("on_success", on_success),
        ("on_failure", on_failure),
    )
    steps.extend(
        project_workflow_step(
            callback_type,
            callback,
            depends_on=parallel_ids,
            callback_type=callback_type,
        )
        for callback_type, callback in callbacks
        if callback is not None
    )
    return WorkflowDefinition(name=name, steps=steps, options=options)


__all__ = ["batch", "chain", "group"]
