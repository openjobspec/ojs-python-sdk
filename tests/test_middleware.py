"""Tests for OJS middleware chains."""

from __future__ import annotations

from ojs.job import Job, JobContext, JobRequest, JobState
from ojs.middleware import EnqueueMiddlewareChain, ExecutionMiddlewareChain


class TestEnqueueMiddleware:
    async def test_empty_chain_calls_final(self) -> None:
        chain = EnqueueMiddlewareChain()
        called = False

        async def final(req: JobRequest) -> Job:
            nonlocal called
            called = True
            return Job(id="test", type=req.type, state=JobState.AVAILABLE, args=req.args)

        result = await chain.execute(JobRequest(type="test", args=[1]), final)
        assert called
        assert result is not None
        assert result.type == "test"

    async def test_middleware_can_modify_request(self) -> None:
        chain = EnqueueMiddlewareChain()

        async def add_meta(request: JobRequest, next) -> Job | None:
            request.meta = {"added": True}
            return await next(request)

        chain.add(add_meta)

        async def final(req: JobRequest) -> Job:
            assert req.meta == {"added": True}
            return Job(id="test", type=req.type, state=JobState.AVAILABLE)

        await chain.execute(JobRequest(type="test", args=[]), final)

    async def test_middleware_order(self) -> None:
        chain = EnqueueMiddlewareChain()
        order: list[str] = []

        async def first(request, next):
            order.append("first")
            return await next(request)

        async def second(request, next):
            order.append("second")
            return await next(request)

        chain.add(first)
        chain.add(second)

        async def final(req):
            order.append("final")
            return Job(id="test", type="test", state=JobState.AVAILABLE)

        await chain.execute(JobRequest(type="test", args=[]), final)
        assert order == ["first", "second", "final"]

    async def test_prepend(self) -> None:
        chain = EnqueueMiddlewareChain()
        order: list[str] = []

        async def first(request, next):
            order.append("first")
            return await next(request)

        async def prepended(request, next):
            order.append("prepended")
            return await next(request)

        chain.add(first)
        chain.prepend(prepended)

        async def final(req):
            return Job(id="test", type="test", state=JobState.AVAILABLE)

        await chain.execute(JobRequest(type="test", args=[]), final)
        assert order == ["prepended", "first"]


class TestExecutionMiddleware:
    async def test_empty_chain_calls_handler(self) -> None:
        chain = ExecutionMiddlewareChain()
        job = Job(id="j1", type="test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            return "done"

        result = await chain.execute(ctx, handler)
        assert result == "done"

    async def test_middleware_wraps_handler(self) -> None:
        chain = ExecutionMiddlewareChain()
        events: list[str] = []

        async def timing_mw(ctx: JobContext, next) -> object:
            events.append("before")
            result = await next()
            events.append("after")
            return result

        chain.add(timing_mw)

        job = Job(id="j1", type="test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c: JobContext) -> str:
            events.append("handler")
            return "result"

        result = await chain.execute(ctx, handler)
        assert result == "result"
        assert events == ["before", "handler", "after"]

    async def test_nested_middleware_onion_pattern(self) -> None:
        chain = ExecutionMiddlewareChain()
        events: list[str] = []

        async def outer(ctx, next):
            events.append("outer-in")
            result = await next()
            events.append("outer-out")
            return result

        async def inner(ctx, next):
            events.append("inner-in")
            result = await next()
            events.append("inner-out")
            return result

        chain.add(outer)
        chain.add(inner)

        job = Job(id="j1", type="test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c):
            events.append("handler")
            return "ok"

        await chain.execute(ctx, handler)
        assert events == ["outer-in", "inner-in", "handler", "inner-out", "outer-out"]

    async def test_middleware_can_catch_errors(self) -> None:
        chain = ExecutionMiddlewareChain()
        caught = False

        async def error_handler(ctx, next):
            nonlocal caught
            try:
                return await next()
            except ValueError:
                caught = True
                return "recovered"

        chain.add(error_handler)

        job = Job(id="j1", type="test", state=JobState.ACTIVE)
        ctx = JobContext(job=job)

        async def handler(c):
            raise ValueError("boom")

        result = await chain.execute(ctx, handler)
        assert caught
        assert result == "recovered"
