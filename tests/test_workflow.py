"""Tests for OJS workflow builders."""

from __future__ import annotations

import ojs


class TestChain:
    def test_chain_creates_sequential_steps(self) -> None:
        definition = ojs.chain(
            "test-chain",
            [
                ojs.JobRequest(type="step.one", args=["a"]),
                ojs.JobRequest(type="step.two", args=["b"]),
                ojs.JobRequest(type="step.three", args=["c"]),
            ],
        )

        assert definition.name == "test-chain"
        assert len(definition.steps) == 3

        # First step has no dependencies
        assert definition.steps[0].id == "step-0"
        assert definition.steps[0].type == "step.one"
        assert definition.steps[0].depends_on == []

        # Subsequent steps depend on the previous
        assert definition.steps[1].depends_on == ["step-0"]
        assert definition.steps[2].depends_on == ["step-1"]

    def test_chain_serialization(self) -> None:
        definition = ojs.chain(
            "my-chain",
            [ojs.JobRequest(type="a", args=[1]), ojs.JobRequest(type="b", args=[2])],
        )
        d = definition.to_dict()
        assert d["name"] == "my-chain"
        assert len(d["steps"]) == 2
        assert d["steps"][0]["depends_on"] == []
        assert d["steps"][1]["depends_on"] == ["step-0"]


class TestGroup:
    def test_group_creates_parallel_steps(self) -> None:
        definition = ojs.group(
            "test-group",
            [
                ojs.JobRequest(type="task.a", args=[1]),
                ojs.JobRequest(type="task.b", args=[2]),
                ojs.JobRequest(type="task.c", args=[3]),
            ],
        )

        assert definition.name == "test-group"
        assert len(definition.steps) == 3

        # All steps have no dependencies (parallel)
        for step in definition.steps:
            assert step.depends_on == []

    def test_group_preserves_job_types(self) -> None:
        definition = ojs.group(
            "g",
            [ojs.JobRequest(type="x", args=[]), ojs.JobRequest(type="y", args=[])],
        )
        assert definition.steps[0].type == "x"
        assert definition.steps[1].type == "y"


class TestBatch:
    def test_batch_with_callbacks(self) -> None:
        definition = ojs.batch(
            "test-batch",
            [
                ojs.JobRequest(type="import.chunk", args=[1]),
                ojs.JobRequest(type="import.chunk", args=[2]),
            ],
            on_complete=ojs.JobRequest(type="import.finalize", args=[]),
            on_success=ojs.JobRequest(type="notify.success", args=[]),
            on_failure=ojs.JobRequest(type="notify.failure", args=[]),
        )

        assert definition.name == "test-batch"
        # 2 parallel + 3 callbacks
        assert len(definition.steps) == 5

        # Parallel steps have no dependencies
        assert definition.steps[0].depends_on == []
        assert definition.steps[1].depends_on == []

        # Callbacks depend on all parallel steps
        on_complete = definition.steps[2]
        assert on_complete.id == "on_complete"
        assert on_complete.depends_on == ["step-0", "step-1"]

        on_success = definition.steps[3]
        assert on_success.id == "on_success"
        assert on_success.depends_on == ["step-0", "step-1"]

        on_failure = definition.steps[4]
        assert on_failure.id == "on_failure"
        assert on_failure.depends_on == ["step-0", "step-1"]

    def test_batch_without_callbacks(self) -> None:
        definition = ojs.batch(
            "simple-batch",
            [
                ojs.JobRequest(type="task.a", args=[]),
                ojs.JobRequest(type="task.b", args=[]),
            ],
        )

        # Just the parallel steps, no callbacks
        assert len(definition.steps) == 2

    def test_batch_partial_callbacks(self) -> None:
        definition = ojs.batch(
            "partial",
            [ojs.JobRequest(type="a", args=[])],
            on_complete=ojs.JobRequest(type="done", args=[]),
        )

        assert len(definition.steps) == 2
        assert definition.steps[1].id == "on_complete"


class TestWorkflowSerialization:
    def test_workflow_step_from_dict(self) -> None:
        data = {
            "id": "step-1",
            "type": "email.send",
            "args": ["user@example.com"],
            "depends_on": ["step-0"],
            "job_id": "019539a4-b68c-7def-8000-1a2b3c4d5e6f",
            "state": "completed",
            "result": {"sent": True},
            "started_at": "2026-02-12T10:00:00Z",
            "completed_at": "2026-02-12T10:00:01Z",
        }
        step = ojs.WorkflowStep.from_dict(data)
        assert step.id == "step-1"
        assert step.type == "email.send"
        assert step.state == "completed"
        assert step.result == {"sent": True}
        assert step.job_id == "019539a4-b68c-7def-8000-1a2b3c4d5e6f"

    def test_workflow_from_dict(self) -> None:
        data = {
            "id": "wf-123",
            "name": "my-workflow",
            "state": "running",
            "steps": [
                {"id": "s1", "type": "a", "args": [], "depends_on": []},
                {"id": "s2", "type": "b", "args": [], "depends_on": ["s1"]},
            ],
            "created_at": "2026-02-12T10:00:00Z",
        }
        wf = ojs.Workflow.from_dict(data)
        assert wf.id == "wf-123"
        assert wf.name == "my-workflow"
        assert wf.state == "running"
        assert len(wf.steps) == 2
        assert wf.steps[1].depends_on == ["s1"]
