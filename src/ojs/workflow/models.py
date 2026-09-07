"""Transport-neutral workflow request and response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ojs.wire_validation import WireDecoder


@dataclass
class WorkflowStep:
    """A workflow step definition or server-returned step status."""

    id: str
    type: str
    args: list[Any] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    options: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    schema: str | None = None

    job_id: str | None = None
    state: str | None = None
    result: Any = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "args": self.args,
            "depends_on": self.depends_on,
        }
        if self.meta is not None:
            data["meta"] = self.meta
        if self.schema is not None:
            data["schema"] = self.schema
        if self.options is not None:
            data["options"] = self.options
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls._from_decoder(WireDecoder.object(data, "workflow_step"))

    @classmethod
    def _from_decoder(cls, decoder: WireDecoder) -> WorkflowStep:
        known_fields = {
            "id",
            "type",
            "args",
            "depends_on",
            "options",
            "meta",
            "schema",
            "job_id",
            "state",
            "result",
            "started_at",
            "completed_at",
            "error",
        }
        return cls(
            id=decoder.required_string("id"),
            type=decoder.required_string("type"),
            args=decoder.array("args"),
            depends_on=decoder.string_array("depends_on"),
            options=decoder.optional_mapping("options"),
            meta=decoder.optional_mapping("meta"),
            schema=decoder.string("schema"),
            job_id=decoder.string("job_id"),
            state=decoder.string("state"),
            result=decoder.value("result"),
            started_at=decoder.datetime("started_at"),
            completed_at=decoder.datetime("completed_at"),
            error=decoder.optional_mapping("error"),
            extra={key: value for key, value in decoder.data.items() if key not in known_fields},
        )


@dataclass
class Workflow:
    """An OJS workflow as returned by a backend."""

    id: str
    name: str
    state: str
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: datetime | None = None
    type: str | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    steps_total: int | None = None
    steps_completed: int | None = None
    jobs_total: int | None = None
    jobs_completed: int | None = None
    steps_cancelled: int | None = None
    steps_already_completed: int | None = None
    callbacks: dict[str, dict[str, Any]] | None = None
    error: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        decoder = WireDecoder.object(data, "workflow")
        known_fields = {
            "id",
            "name",
            "state",
            "steps",
            "created_at",
            "type",
            "completed_at",
            "cancelled_at",
            "steps_total",
            "steps_completed",
            "jobs_total",
            "jobs_completed",
            "steps_cancelled",
            "steps_already_completed",
            "callbacks",
            "error",
        }
        raw_steps = decoder.array("steps")
        steps = [
            WorkflowStep._from_decoder(WireDecoder.object(step, f"workflow.steps[{index}]"))
            for index, step in enumerate(raw_steps)
        ]
        callbacks = decoder.optional_mapping("callbacks")
        if callbacks is not None:
            callbacks = {
                key: dict(WireDecoder.object(value, f"workflow.callbacks.{key}").data)
                for key, value in callbacks.items()
            }
        return cls(
            id=decoder.required_string("id"),
            name=decoder.required_string("name"),
            state=decoder.required_string("state"),
            steps=steps,
            created_at=decoder.datetime("created_at"),
            type=decoder.string("type"),
            completed_at=decoder.datetime("completed_at"),
            cancelled_at=decoder.datetime("cancelled_at"),
            steps_total=decoder.integer("steps_total"),
            steps_completed=decoder.integer("steps_completed"),
            jobs_total=decoder.integer("jobs_total"),
            jobs_completed=decoder.integer("jobs_completed"),
            steps_cancelled=decoder.integer("steps_cancelled"),
            steps_already_completed=decoder.integer("steps_already_completed"),
            callbacks=callbacks,
            error=decoder.optional_mapping("error"),
            extra={key: value for key, value in decoder.data.items() if key not in known_fields},
        )


@dataclass
class WorkflowDefinition:
    """A flat workflow DAG ready to be submitted to the HTTP binding."""

    name: str
    steps: list[WorkflowStep]
    options: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.options is not None:
            data["options"] = self.options
        return data


__all__ = ["Workflow", "WorkflowDefinition", "WorkflowStep"]
