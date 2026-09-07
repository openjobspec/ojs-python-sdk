"""Tests for OJS workflow builders."""

from __future__ import annotations

import ojs


def _fully_populated_request(job_type: str = "task.full") -> ojs.JobRequest:
    return ojs.JobRequest(
        type=job_type,
        args=[{"payload": True}],
        queue="critical",
        meta={"trace_id": "trace-1", "nested": {"value": 1}},
        priority=7,
        timeout_ms=45000,
        delay_until="2026-02-12T10:00:00Z",
        expires_at="2026-02-13T10:00:00Z",
        retry=ojs.RetryPolicy(
            max_attempts=5,
            initial_interval="PT2S",
            jitter=False,
        ),
        unique=ojs.UniquePolicy(
            keys=["type", "args"],
            args_keys=["payload"],
            period="PT1H",
        ),
        tags=["full", "workflow"],
        schema="task.full.v1",
    )


def _assert_complete_projection(
    step: dict[str, object],
    *,
    callback_type: str | None = None,
) -> None:
    assert step["meta"] == {"trace_id": "trace-1", "nested": {"value": 1}}
    assert step["schema"] == "task.full.v1"
    options = dict(step["options"])
    if callback_type is not None:
        assert options.pop("callback_type") == callback_type
    assert options == {
        "queue": "critical",
        "priority": 7,
        "timeout_ms": 45000,
        "delay_until": "2026-02-12T10:00:00Z",
        "expires_at": "2026-02-13T10:00:00Z",
        "retry": {
            "max_attempts": 5,
            "initial_interval": "PT2S",
            "backoff_coefficient": 2.0,
            "max_interval": "PT5M",
            "jitter": False,
        },
        "unique": {
            "on_conflict": "reject",
            "key": ["type", "args"],
            "period": "PT1H",
            "states": ["available", "active", "scheduled"],
            "args_keys": ["payload"],
        },
        "tags": ["full", "workflow"],
    }


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

    def test_chain_preserves_every_job_request_field(self) -> None:
        definition = ojs.chain("full-chain", [_fully_populated_request()])

        step = definition.to_dict()["steps"][0]
        _assert_complete_projection(step)


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

    def test_group_preserves_every_job_request_field(self) -> None:
        definition = ojs.group("full-group", [_fully_populated_request()])

        step = definition.to_dict()["steps"][0]
        _assert_complete_projection(step)


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

    def test_batch_jobs_and_callbacks_preserve_every_request_field(self) -> None:
        definition = ojs.batch(
            "full-batch",
            [_fully_populated_request("batch.item")],
            on_complete=_fully_populated_request("batch.callback"),
        )

        body = definition.to_dict()
        _assert_complete_projection(body["steps"][0])
        _assert_complete_projection(body["steps"][1], callback_type="on_complete")
        callback_options = body["steps"][1]["options"]
        assert callback_options["callback_type"] == "on_complete"


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

    def test_failed_workflow_response_preserves_status_details(self) -> None:
        workflow = ojs.Workflow.from_dict(
            {
                "id": "wf-failed",
                "name": "failure-case",
                "type": "chain",
                "state": "failed",
                "steps_total": 2,
                "steps_completed": 1,
                "completed_at": "2026-02-12T10:01:00Z",
                "error": {"code": "step_failed", "step_id": "step-1"},
                "backend_extension": {"trace": "abc"},
                "steps": [
                    {
                        "id": "step-1",
                        "type": "task.fail",
                        "state": "failed",
                        "job_id": "job-1",
                        "error": {"code": "handler_error", "message": "boom"},
                        "failure_detail": {"attempt": 3},
                    }
                ],
            }
        )

        assert workflow.type == "chain"
        assert workflow.steps_total == 2
        assert workflow.steps_completed == 1
        assert workflow.error == {"code": "step_failed", "step_id": "step-1"}
        assert workflow.extra == {"backend_extension": {"trace": "abc"}}
        assert workflow.steps[0].error == {
            "code": "handler_error",
            "message": "boom",
        }
        assert workflow.steps[0].extra == {"failure_detail": {"attempt": 3}}

    def test_cancelled_workflow_response_shape(self) -> None:
        workflow = ojs.Workflow.from_dict(
            {
                "id": "wf-cancelled",
                "name": "cancel-case",
                "state": "cancelled",
                "cancelled_at": "2026-02-12T10:31:00Z",
                "steps_cancelled": 2,
                "steps_already_completed": 1,
            }
        )

        assert workflow.state == "cancelled"
        assert workflow.cancelled_at is not None
        assert workflow.steps_cancelled == 2
        assert workflow.steps_already_completed == 1
