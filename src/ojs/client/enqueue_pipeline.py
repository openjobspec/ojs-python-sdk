"""Shared enqueue validation, middleware, and sink pipeline."""

from __future__ import annotations

import asyncio
import copy
import re
from dataclasses import dataclass
from typing import Protocol

from ojs.errors import OJSError, OJSValidationError
from ojs.job import Job, JobRequest
from ojs.middleware import EnqueueMiddlewareChain, EnqueueNext
from ojs.transport.fake import FakeTransport, current_fake_transport

_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_QUEUE_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9]*[-.]?[a-z0-9]+)*$")
_MAX_TYPE_LENGTH = 255
_MAX_QUEUE_LENGTH = 128


class EnqueueTransport(Protocol):
    async def push(self, body: dict[str, object]) -> Job: ...

    async def push_batch(self, jobs: list[dict[str, object]]) -> list[Job]: ...


class EnqueueSink(Protocol):
    async def push(self, request: JobRequest) -> Job: ...

    async def push_batch(self, requests: list[JobRequest]) -> list[Job]: ...


class TransportEnqueueSink:
    """Dispatch validated envelopes to a production transport."""

    def __init__(self, transport: EnqueueTransport) -> None:
        self._transport = transport

    async def push(self, request: JobRequest) -> Job:
        return await self._transport.push(request.to_dict())

    async def push_batch(self, requests: list[JobRequest]) -> list[Job]:
        return await self._transport.push_batch([request.to_dict() for request in requests])


class FakeEnqueueSink(TransportEnqueueSink):
    """Dispatch envelopes to an explicit in-memory fake transport."""

    def __init__(self, transport: FakeTransport) -> None:
        super().__init__(transport)


class ContextualEnqueueSink:
    """Route implicit clients through the currently active fake transport."""

    def __init__(
        self,
        transport: EnqueueTransport,
        *,
        allow_context_fake: bool,
    ) -> None:
        self._transport = transport
        self._allow_context_fake = allow_context_fake

    def _selected(self) -> EnqueueSink:
        fake = current_fake_transport() if self._allow_context_fake else None
        if fake is not None:
            return FakeEnqueueSink(fake)
        return TransportEnqueueSink(self._transport)

    async def push(self, request: JobRequest) -> Job:
        return await self._selected().push(request)

    async def push_batch(self, requests: list[JobRequest]) -> list[Job]:
        return await self._selected().push_batch(requests)


@dataclass(slots=True)
class _BatchTerminal:
    """One batch item's validated request plus its deferred transport result.

    Created when an item's middleware chain reaches the terminal
    ``dispatch`` call. The ``future`` is resolved later (after the single
    atomic ``push_batch`` call) with the real transport-returned ``Job``,
    letting outer middleware's post-``next()`` code observe it.
    """

    request: JobRequest
    future: asyncio.Future[Job]


class EnqueuePipeline:
    """Apply the same request pipeline to single and batch enqueue operations."""

    def __init__(
        self,
        middleware: EnqueueMiddlewareChain,
        sink: EnqueueSink,
    ) -> None:
        self._middleware = middleware
        self._sink = sink

    async def enqueue(self, request: JobRequest) -> Job:
        working = copy.deepcopy(request)
        validate_request(working)

        async def dispatch(candidate: JobRequest) -> Job:
            validate_request(candidate)
            return await self._sink.push(copy.deepcopy(candidate))

        result = await self._middleware.execute(working, dispatch)
        if result is None:
            raise OJSError("Enqueue middleware rejected the request")
        return result

    async def enqueue_batch(self, requests: list[JobRequest]) -> list[Job]:
        """Run each item's middleware chain to a barrier around one atomic push.

        Every request's middleware chain is driven concurrently up to its
        terminal ("dispatch") call. Once every chain has either reached its
        terminal or settled without one, a single atomic
        ``push_batch`` transport call is issued for every item that reached
        its terminal. Each terminal is then resolved with its *real*
        transport-returned ``Job`` (not a fabricated placeholder), which
        lets outer middleware's post-``next()`` code observe the genuine
        result and apply return-value transformations — mirroring how the
        single-item ``enqueue`` path already works, and mirroring the
        JS SDK's barrier-based batch orchestration.

        Semantics preserved from the previous implementation:

        - Exactly one atomic transport call is made for the whole batch.
        - A middleware that short-circuits *before* reaching the terminal by
          returning ``None`` is treated as an outright rejection: the whole
          batch is aborted (nothing is sent to the transport) and an
          ``OJSError`` is raised, matching ``enqueue()``'s single-item
          "middleware rejected the request" behavior.
        - A middleware that short-circuits before the terminal with a
          non-``None`` value (a "replace" middleware that fabricates its own
          result) is honored as-is and never sent to the transport.
        - Results are returned in the original request order.

        New/clarified semantics (the "drop" case, only reachable once a
        terminal genuinely resolves with a transport-created job): if outer
        middleware's post-``next()`` code returns ``None`` *after* the
        terminal already resolved, the job was already durably created by
        the one atomic transport call and cannot be un-created. That case is
        therefore not an error: the item is silently omitted from the
        returned list, since raising would incorrectly imply nothing was
        enqueued.
        """
        n = len(requests)
        if n == 0:
            return []

        loop = asyncio.get_running_loop()
        gates = [asyncio.Event() for _ in range(n)]
        decided = [False] * n
        terminals: list[_BatchTerminal | None] = [None] * n
        final_results: list[Job | None] = [None] * n
        chain_errors: list[BaseException | None] = [None] * n

        def decide(index: int) -> None:
            if not decided[index]:
                decided[index] = True
                gates[index].set()

        def make_dispatch(index: int) -> EnqueueNext:
            reached = False
            terminal_error: BaseException | None = None

            async def dispatch(candidate: JobRequest) -> Job:
                # A retry-style middleware that catches a rejection and calls
                # next() again would otherwise re-enter this terminal after
                # the batch's single atomic transport attempt was already
                # started. Whole-batch transport retry is unsupported: the
                # re-invocation is rejected with the ORIGINAL terminal error
                # (or a generic one if the terminal had not yet failed) so a
                # retry observes a deterministic failure instead of hanging.
                nonlocal reached, terminal_error
                if reached:
                    if terminal_error is not None:
                        raise terminal_error
                    raise OJSError(
                        "Batch enqueue terminal re-invoked before its single "
                        "atomic transport attempt settled; whole-batch "
                        "transport retry is not supported."
                    )
                reached = True
                try:
                    validate_request(candidate)
                except Exception as exc:
                    terminal_error = exc
                    raise
                future: asyncio.Future[Job] = loop.create_future()
                terminals[index] = _BatchTerminal(copy.deepcopy(candidate), future)
                decide(index)
                return await future

            return dispatch

        async def run_chain(index: int) -> None:
            working = copy.deepcopy(requests[index])
            try:
                validate_request(working)
                final_results[index] = await self._middleware.execute(working, make_dispatch(index))
            except Exception as exc:
                chain_errors[index] = exc
            finally:
                decide(index)

        tasks = [asyncio.ensure_future(run_chain(i)) for i in range(n)]
        try:
            await asyncio.gather(*(gate.wait() for gate in gates))

            # A middleware/validation failure (real exception, or a `None`
            # short-circuit before reaching the terminal) aborts the whole
            # batch before any transport call is made.
            for index in range(n):
                if terminals[index] is not None:
                    continue
                if chain_errors[index] is None and final_results[index] is None:
                    chain_errors[index] = OJSError(
                        f"Enqueue middleware rejected batch item at index {index}"
                    )
            first_error = next((e for e in chain_errors if e is not None), None)
            if first_error is not None:
                for terminal in terminals:
                    if terminal is not None and not terminal.future.done():
                        terminal.future.set_exception(first_error)
                await asyncio.gather(*tasks, return_exceptions=True)
                raise first_error

            pending = [(i, t) for i, t in enumerate(terminals) if t is not None]
            if pending:
                try:
                    dispatched = await self._sink.push_batch([t.request for _, t in pending])
                    if len(dispatched) != len(pending):
                        raise OJSError(
                            "Batch enqueue transport returned a different number "
                            f"of jobs ({len(dispatched)} != {len(pending)})"
                        )
                except Exception as exc:
                    for _, terminal in pending:
                        if not terminal.future.done():
                            terminal.future.set_exception(exc)
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise
                for (_, terminal), job in zip(pending, dispatched, strict=True):
                    if not terminal.future.done():
                        terminal.future.set_result(job)

            # Let each chain's post-next code run (observe the real
            # transport-returned job, apply any return-value
            # transformation) before assembling the final results.
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        post_error = next((e for e in chain_errors if e is not None), None)
        if post_error is not None:
            raise post_error

        results: list[Job] = []
        for index in range(n):
            result = final_results[index]
            if result is None:
                # Either a pre-terminal `None` (already raised above via
                # `chain_errors`) or a post-terminal drop: the job was
                # already durably created by the atomic transport call and
                # is silently omitted rather than raised as an error.
                continue
            results.append(result)
        return results


def validate_request(request: JobRequest) -> None:
    job_type = request.type
    queue = request.queue
    if not job_type or not job_type.strip():
        raise OJSValidationError("job_type must not be empty")
    if len(job_type) > _MAX_TYPE_LENGTH:
        raise OJSValidationError(
            f"job_type must not exceed {_MAX_TYPE_LENGTH} characters, got {len(job_type)}"
        )
    if _TYPE_PATTERN.fullmatch(job_type) is None:
        raise OJSValidationError(
            f"invalid job_type {job_type!r}: must match pattern "
            "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$"
        )
    if not queue or not queue.strip():
        raise OJSValidationError("queue must not be empty")
    if len(queue) > _MAX_QUEUE_LENGTH:
        raise OJSValidationError(
            f"queue must not exceed {_MAX_QUEUE_LENGTH} characters, got {len(queue)}"
        )
    if _QUEUE_PATTERN.fullmatch(queue) is None:
        raise OJSValidationError(
            f"invalid queue {queue!r}: must match pattern ^[a-z0-9][a-z0-9\\-.]*$"
        )


__all__ = [
    "ContextualEnqueueSink",
    "EnqueuePipeline",
    "EnqueueSink",
    "FakeEnqueueSink",
    "TransportEnqueueSink",
    "validate_request",
]
