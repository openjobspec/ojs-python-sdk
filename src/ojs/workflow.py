"""OJS workflow types and builder functions.

Provides chain(), group(), and batch() builders for composing
multi-step job workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ojs._utils import parse_datetime
from ojs.job import JobRequest


@dataclass
class WorkflowStep:
    """A single step in a workflow definition."""

    id: str
    type: str
    args: list[Any] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    options: dict[str, Any] | None = None

    # Set after workflow creation by the server
    job_id: str | None = None
    state: str | None = None
    result: Any = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "args": self.args,
            "depends_on": self.depends_on,
        }
        if self.options:
            d["options"] = self.options
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            id=data["id"],
            type=data["type"],
            args=data.get("args", []),
            depends_on=data.get("depends_on", []),
            options=data.get("options"),
            job_id=data.get("job_id"),
            state=data.get("state"),
            result=data.get("result"),
            started_at=parse_datetime(data.get("started_at")),
            completed_at=parse_datetime(data.get("completed_at")),
        )


@dataclass
class Workflow:
    """An OJS workflow as returned by the server."""

    id: str
    name: str
    state: str
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        return cls(
            id=data["id"],
            name=data["name"],
            state=data["state"],
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            created_at=parse_datetime(data.get("created_at")),
        )


@dataclass
class WorkflowDefinition:
    """A workflow definition ready to be submitted to the server."""

    name: str
    steps: list[WorkflowStep]
    options: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
        }
        if self.options:
            d["options"] = self.options
        return d


def chain(
    name: str,
    jobs: list[JobRequest],
    *,
    options: dict[str, Any] | None = None,
) -> WorkflowDefinition:
    """Build a chain (sequential) workflow.

    Jobs execute one after another. Each job receives the result of the
    previous job as input.

    Args:
        name: Human-readable workflow name.
        jobs: Ordered list of job requests.
        options: Default enqueue options for all steps.

    Returns:
        A WorkflowDefinition ready to be submitted.
    """
    steps: list[WorkflowStep] = []
    for i, job in enumerate(jobs):
        step_id = f"step-{i}"
        depends = [f"step-{i - 1}"] if i > 0 else []
        step_options = {}
        if job.queue != "default":
            step_options["queue"] = job.queue
        if job.retry:
            step_options["retry"] = job.retry.to_dict()
        steps.append(
            WorkflowStep(
                id=step_id,
                type=job.type,
                args=job.args,
                depends_on=depends,
                options=step_options or None,
            )
        )
    return WorkflowDefinition(name=name, steps=steps, options=options)


def group(
    name: str,
    jobs: list[JobRequest],
    *,
    options: dict[str, Any] | None = None,
) -> WorkflowDefinition:
    """Build a group (parallel) workflow.

    All jobs execute concurrently with no ordering guarantees.

    Args:
        name: Human-readable workflow name.
        jobs: List of job requests to run in parallel.
        options: Default enqueue options for all steps.

    Returns:
        A WorkflowDefinition ready to be submitted.
    """
    steps: list[WorkflowStep] = []
    for i, job in enumerate(jobs):
        step_options = {}
        if job.queue != "default":
            step_options["queue"] = job.queue
        if job.retry:
            step_options["retry"] = job.retry.to_dict()
        steps.append(
            WorkflowStep(
                id=f"step-{i}",
                type=job.type,
                args=job.args,
                depends_on=[],
                options=step_options or None,
            )
        )
    return WorkflowDefinition(name=name, steps=steps, options=options)


def batch(
    name: str,
    jobs: list[JobRequest],
    *,
    on_complete: JobRequest | None = None,
    on_success: JobRequest | None = None,
    on_failure: JobRequest | None = None,
    options: dict[str, Any] | None = None,
) -> WorkflowDefinition:
    """Build a batch workflow (group with callbacks).

    All jobs execute concurrently. Callback jobs fire when all jobs
    reach terminal states.

    Args:
        name: Human-readable workflow name.
        jobs: List of job requests to run in parallel.
        on_complete: Job to run when all jobs reach terminal state.
        on_success: Job to run when all jobs complete successfully.
        on_failure: Job to run when any job fails/is discarded.
        options: Default enqueue options for all steps.

    Returns:
        A WorkflowDefinition ready to be submitted.
    """
    steps: list[WorkflowStep] = []
    parallel_ids: list[str] = []

    for i, job in enumerate(jobs):
        step_id = f"step-{i}"
        parallel_ids.append(step_id)
        step_options = {}
        if job.queue != "default":
            step_options["queue"] = job.queue
        if job.retry:
            step_options["retry"] = job.retry.to_dict()
        steps.append(
            WorkflowStep(
                id=step_id,
                type=job.type,
                args=job.args,
                depends_on=[],
                options=step_options or None,
            )
        )

    # Add callback steps that depend on all parallel jobs
    for cb_name, cb_job in [
        ("on_complete", on_complete),
        ("on_success", on_success),
        ("on_failure", on_failure),
    ]:
        if cb_job is not None:
            cb_options: dict[str, Any] = {"callback_type": cb_name}
            if cb_job.queue != "default":
                cb_options["queue"] = cb_job.queue
            steps.append(
                WorkflowStep(
                    id=cb_name,
                    type=cb_job.type,
                    args=cb_job.args,
                    depends_on=parallel_ids,
                    options=cb_options,
                )
            )

    return WorkflowDefinition(name=name, steps=steps, options=options)
