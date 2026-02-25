"""Tests for the OJS Worker."""

from __future__ import annotations

import ojs
from ojs.job import Job, JobContext, JobState
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
        async def mw(ctx, next):
            return await next()

        assert len(worker._execution_middleware._middlewares) == 1


class TestWorkerProcessJob:
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
        async def my_mw(ctx, next):
            nonlocal mw_ran
            mw_ran = True
            return await next()

        @worker.register("test.echo")
        async def handler(ctx: ojs.JobContext) -> str:
            return "ok"

        job = Job(id="job-4", type="test.echo", state=JobState.ACTIVE, args=[])
        await worker._process_job(job)

        assert mw_ran
        assert len(transport.acked) == 1


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

