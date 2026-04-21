"""Tests for the OJS Worker."""

from __future__ import annotations

import asyncio
from math import inf, nan
from unittest.mock import AsyncMock, patch

import pytest

import ojs
from ojs.errors import OJSCapabilityError, OJSConnectionError
from ojs.job import Job, JobContext, JobState
from ojs.worker.completion_reporter import Completed, CompletionReporter, Failed
from tests.conftest import FakeTransport


class TestWorkerRegistration:
    def test_register_handler(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("email.send")
        async def handle(ctx: ojs.JobContext) -> None:
            pass

        assert "email.send" in worker._handlers

    def test_register_multiple_handlers(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("email.send")
        async def h1(ctx: ojs.JobContext) -> None:
            pass

        @worker.register("report.generate")
        async def h2(ctx: ojs.JobContext) -> None:
            pass

        assert len(worker._handlers) == 2

    def test_register_middleware(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.middleware
        async def mw(ctx, next_fn):
            return await next_fn()

        assert len(worker._execution_middleware._middlewares) == 1


class TestWorkerOptionValidation:
    @pytest.mark.parametrize(
        ("option", "value", "message"),
        [
            ("concurrency", 0, "concurrency"),
            ("concurrency", -1, "concurrency"),
            ("concurrency", True, "concurrency"),
            ("poll_interval", 0, "poll_interval"),
            ("poll_interval", nan, "poll_interval"),
            ("heartbeat_interval", -1, "heartbeat_interval"),
            ("heartbeat_interval", inf, "heartbeat_interval"),
            ("visibility_timeout_ms", 0, "visibility_timeout_ms"),
            ("visibility_timeout_ms", True, "visibility_timeout_ms"),
            ("visibility_timeout", 0, "visibility_timeout"),
            ("visibility_timeout", 0.0001, "at least 1 millisecond"),
            ("timeout", 0, "timeout"),
            ("grace_period", -1, "grace_period"),
        ],
    )
    def test_rejects_invalid_options(
        self,
        option: str,
        value: object,
        message: str,
    ) -> None:
        with pytest.raises(ValueError, match=message):
            ojs.Worker(
                "http://localhost:8080",
                transport=FakeTransport(),
                **{option: value},
            )

    def test_rejects_both_visibility_timeout_forms(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ojs.Worker(
                "http://localhost:8080",
                transport=FakeTransport(),
                visibility_timeout=30,
                visibility_timeout_ms=30000,
            )

    def test_converts_visibility_timeout_seconds(self) -> None:
        worker = ojs.Worker(
            "http://localhost:8080",
            transport=FakeTransport(),
            visibility_timeout=1.5,
            grace_period=0,
        )

        assert worker._visibility_timeout_ms == 1500


class TestWorkerProcessJob:
    async def test_handler_attempt_is_one_indexed(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)
        observed_attempts: list[int] = []

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            observed_attempts.append(ctx.attempt)
            return "ok"

        await worker._process_job(Job(id="job-attempt", type="test.echo", state=JobState.ACTIVE))

        assert observed_attempts == [1]

    async def test_process_job_acks_on_success(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> dict[str, str]:
            return {"echoed": True}

        job = Job(id="job-1", type="test.echo", state=JobState.ACTIVE, args=["hello"])
        await worker._process_job(job)

        assert len(transport.acked) == 1
        assert transport.acked[0]["job_id"] == "job-1"
        assert transport.acked[0]["result"] == {"echoed": True}

    async def test_process_job_nacks_on_error(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.fail")
        async def handler(ctx: ojs.JobContext) -> None:
            raise RuntimeError("something went wrong")

        job = Job(id="job-2", type="test.fail", state=JobState.ACTIVE, args=[])
        await worker._process_job(job)

        assert len(transport.nacked) == 1
        assert transport.nacked[0]["job_id"] == "job-2"
        assert "something went wrong" in transport.nacked[0]["error"]["message"]

    async def test_process_job_nacks_for_unknown_type(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        job = Job(id="job-3", type="unknown.type", state=JobState.ACTIVE, args=[])
        await worker._process_job(job)

        assert len(transport.nacked) == 1
        assert "No handler" in transport.nacked[0]["error"]["message"]

    async def test_middleware_runs_during_processing(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)
        mw_ran = False

        @worker.middleware
        async def my_mw(ctx, next_fn):
            nonlocal mw_ran
            mw_ran = True
            return await next_fn()

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        job = Job(id="job-4", type="test.echo", state=JobState.ACTIVE, args=[])
        await worker._process_job(job)

        assert mw_ran
        assert len(transport.acked) == 1

    async def test_handler_reports_progress_through_context(self) -> None:
        transport = FakeTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.progress")
        async def handler(ctx: ojs.JobContext) -> str:
            await ctx.report_progress(
                40,
                message="processing",
                data={"records": 8},
            )
            return "done"

        await worker._process_job(
            Job(id="job-progress", type="test.progress", state=JobState.ACTIVE)
        )

        assert transport.progress_updates == [
            {
                "job_id": "job-progress",
                "percentage": 40,
                "message": "processing",
                "data": {"records": 8},
            }
        ]
        assert transport.acked[0]["result"] == "done"

    async def test_ack_failure_never_sends_nack(self) -> None:
        class FailingAckTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.ack_attempts = 0

            async def ack(self, job_id: str, result: object = None) -> dict[str, object]:
                self.ack_attempts += 1
                raise OJSConnectionError("ack unavailable")

        transport = FailingAckTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "completed"

        with patch(
            "ojs.worker.completion_reporter.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            await worker._process_job(Job(id="job-ack", type="test.echo", state=JobState.ACTIVE))

        assert transport.ack_attempts == 3
        assert transport.nacked == []

    async def test_lost_ack_response_retries_same_outcome(self) -> None:
        class LostAckTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.ack_attempts = 0

            async def ack(self, job_id: str, result: object = None) -> dict[str, object]:
                self.ack_attempts += 1
                if self.ack_attempts == 1:
                    self.acked.append({"job_id": job_id, "result": result})
                    raise OJSConnectionError("response lost after commit")
                return {"acknowledged": True}

        transport = LostAckTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "completed"

        with patch(
            "ojs.worker.completion_reporter.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            await worker._process_job(
                Job(id="job-lost-ack", type="test.echo", state=JobState.ACTIVE)
            )

        assert transport.ack_attempts == 2
        assert transport.nacked == []

    async def test_cancellation_racing_ack_does_not_send_nack(self) -> None:
        class BlockingAckTransport(FakeTransport):
            def __init__(self) -> None:
                super().__init__()
                self.ack_started = asyncio.Event()

            async def ack(self, job_id: str, result: object = None) -> dict[str, object]:
                self.ack_started.set()
                await asyncio.Event().wait()
                return {"acknowledged": True}

        transport = BlockingAckTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "completed"

        task = asyncio.create_task(
            worker._process_job(Job(id="job-race", type="test.echo", state=JobState.ACTIVE))
        )
        await transport.ack_started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert transport.nacked == []

    async def test_only_one_terminal_outcome_wins_race(self) -> None:
        transport = FakeTransport()
        reporter = CompletionReporter(transport, "job-terminal")

        results = await asyncio.gather(
            reporter.report(Completed({"ok": True})),
            reporter.report(
                Failed(
                    {
                        "code": "handler_error",
                        "message": "failed",
                        "retryable": True,
                    }
                )
            ),
        )

        assert sorted(results) == [False, True]
        assert len(transport.acked) + len(transport.nacked) == 1


class TestJobContext:
    def test_context_properties(self) -> None:
        job = Job(
            id="j1",
            type="email.send",
            state=JobState.ACTIVE,
            args=["user@example.com", "welcome"],
            meta={"trace_id": "abc"},
        )
        ctx = JobContext(job=job, attempt=2)

        assert ctx.job_id == "j1"
        assert ctx.job_type == "email.send"
        assert ctx.args == ["user@example.com", "welcome"]
        assert ctx.meta == {"trace_id": "abc"}
        assert ctx.attempt == 2
        assert not ctx.is_cancelled

    def test_context_cancel(self) -> None:
        job = Job(id="j1", type="test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        assert not ctx.is_cancelled
        ctx.cancel()
        assert ctx.is_cancelled

    async def test_progress_requires_active_worker_execution(self) -> None:
        ctx = JobContext(
            job=Job(id="j1", type="test", state=JobState.ACTIVE),
        )

        with pytest.raises(
            OJSCapabilityError,
            match="outside an active worker execution",
        ):
            await ctx.report_progress(10)
