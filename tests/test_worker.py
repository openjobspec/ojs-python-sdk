"""Tests for the OJS Worker."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import ojs
from ojs.job import Job, JobContext, JobState
from ojs.transport.base import Transport


class MockTransport(Transport):
    """Mock transport that returns configurable responses."""

    def __init__(self) -> None:
        self.acked: list[dict[str, Any]] = []
        self.nacked: list[dict[str, Any]] = []
        self.fetched_count = 0
        self._fetch_jobs: list[Job] = []

    def set_fetch_jobs(self, jobs: list[Job]) -> None:
        self._fetch_jobs = jobs

    async def push(self, body):
        return Job.from_dict({"id": "test-id", "type": body["type"], "state": "available", "args": body["args"]})

    async def push_batch(self, jobs):
        return [await self.push(j) for j in jobs]

    async def info(self, job_id):
        return Job(id=job_id, type="test", state=JobState.COMPLETED)

    async def cancel(self, job_id):
        return Job(id=job_id, type="test", state=JobState.CANCELLED)

    async def fetch(self, queues, count=1, worker_id=None, visibility_timeout_ms=30000):
        self.fetched_count += 1
        if self._fetch_jobs:
            jobs = self._fetch_jobs[:count]
            self._fetch_jobs = self._fetch_jobs[count:]
            return jobs
        return []

    async def ack(self, job_id, result=None):
        self.acked.append({"job_id": job_id, "result": result})
        return {"acknowledged": True, "job_id": job_id, "state": "completed"}

    async def nack(self, job_id, error):
        self.nacked.append({"job_id": job_id, "error": error})
        return {"job_id": job_id, "state": "retryable"}

    async def heartbeat(self, worker_id, active_jobs=None, visibility_timeout_ms=None):
        return {"state": "running", "jobs_extended": active_jobs or []}

    async def list_queues(self):
        return []

    async def queue_stats(self, queue_name):
        return ojs.QueueStats(queue=queue_name, status="active")

    async def pause_queue(self, queue_name):
        return {}

    async def resume_queue(self, queue_name):
        return {}

    async def create_workflow(self, definition):
        return ojs.Workflow(id="wf-1", name=definition.name, state="running")

    async def get_workflow(self, workflow_id):
        return ojs.Workflow(id=workflow_id, name="test", state="running")

    async def cancel_workflow(self, workflow_id):
        return {}

    async def health(self):
        return {"status": "ok"}

    async def close(self):
        pass


class TestWorkerRegistration:
    def test_register_handler(self) -> None:
        transport = MockTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("email.send")
        async def handle(ctx: ojs.JobContext) -> None:
            pass

        assert "email.send" in worker._handlers

    def test_register_multiple_handlers(self) -> None:
        transport = MockTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.register("email.send")
        async def h1(ctx: ojs.JobContext) -> None:
            pass

        @worker.register("report.generate")
        async def h2(ctx: ojs.JobContext) -> None:
            pass

        assert len(worker._handlers) == 2

    def test_register_middleware(self) -> None:
        transport = MockTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        @worker.middleware
        async def mw(ctx, next):
            return await next()

        assert len(worker._execution_middleware._middlewares) == 1


class TestWorkerProcessJob:
    async def test_process_job_acks_on_success(self) -> None:
        transport = MockTransport()
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
        transport = MockTransport()
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
        transport = MockTransport()
        worker = ojs.Worker("http://localhost:8080", transport=transport)

        job = Job(id="job-3", type="unknown.type", state=JobState.ACTIVE, args=[])
        await worker._process_job(job)

        assert len(transport.nacked) == 1
        assert "No handler" in transport.nacked[0]["error"]["message"]

    async def test_middleware_runs_during_processing(self) -> None:
        transport = MockTransport()
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
