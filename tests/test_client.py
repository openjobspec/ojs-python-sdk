"""Tests for the OJS Client."""

from __future__ import annotations

import asyncio
import copy
import dataclasses
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

import ojs
from ojs.encryption import EncryptionCodec, StaticKeyProvider, encryption_middleware
from ojs.transport.fake import FakeTransport as ExplicitFakeTransport
from tests.conftest import FakeTransport


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def client(transport: FakeTransport) -> ojs.Client:
    return ojs.Client("http://localhost:8080", transport=transport)


class TestEnqueue:
    async def test_enqueue_simple(self, client: ojs.Client, transport: FakeTransport) -> None:
        job = await client.enqueue("email.send", ["user@example.com", "welcome"])

        assert job.type == "email.send"
        assert job.args == ["user@example.com", "welcome"]
        assert job.state == ojs.JobState.AVAILABLE
        assert len(transport.pushed) == 1
        assert transport.pushed[0]["type"] == "email.send"

    async def test_enqueue_with_options(self, client: ojs.Client, transport: FakeTransport) -> None:
        job = await client.enqueue(
            "email.send",
            ["user@example.com"],
            queue="email",
            retry=ojs.RetryPolicy(max_attempts=5),
            tags=["onboarding"],
        )

        assert job.type == "email.send"
        body = transport.pushed[0]
        assert body["options"]["queue"] == "email"
        assert body["options"]["retry"]["max_attempts"] == 5
        assert body["options"]["tags"] == ["onboarding"]

    async def test_enqueue_empty_args(self, client: ojs.Client) -> None:
        job = await client.enqueue("system.health_check")
        assert job.args == []

    async def test_enqueue_batch(self, client: ojs.Client, transport: FakeTransport) -> None:
        jobs = await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["a@b.com"]),
                ojs.JobRequest(type="email.send", args=["c@d.com"]),
            ]
        )

        assert len(jobs) == 2
        assert len(transport.pushed) == 2


class TestEnqueueMiddleware:
    async def test_middleware_modifies_request(self, transport: FakeTransport) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def add_trace(request, next_fn):
            request.meta = request.meta or {}
            request.meta["trace_id"] = "abc123"
            return await next_fn(request)

        await client.enqueue("test.echo", ["hello"])

        body = transport.pushed[0]
        assert body["meta"]["trace_id"] == "abc123"

    async def test_batch_runs_middleware_once_per_item(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)
        calls: list[str] = []

        @client.enqueue_middleware
        async def record(request, next_fn):
            calls.append(request.type)
            request.meta = {"pipeline": "shared"}
            return await next_fn(request)

        await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["a@example.com"]),
                ojs.JobRequest(type="email.send", args=["b@example.com"]),
            ]
        )

        assert calls == ["email.send", "email.send"]
        assert [body["meta"] for body in transport.pushed] == [
            {"pipeline": "shared"},
            {"pipeline": "shared"},
        ]

    async def test_single_and_batch_payloads_match(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def add_metadata(request, next_fn):
            request.meta = {"source": "middleware"}
            return await next_fn(request)

        await client.enqueue("email.send", ["a@example.com"], queue="email")
        await client.enqueue_batch(
            [
                ojs.JobRequest(
                    type="email.send",
                    args=["a@example.com"],
                    queue="email",
                )
            ]
        )

        assert transport.pushed[0] == transport.pushed[1]

    async def test_middleware_rejection_prevents_batch_dispatch(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def reject(request, next_fn):
            return None

        with pytest.raises(ojs.OJSError, match="batch item"):
            await client.enqueue_batch([ojs.JobRequest(type="email.send", args=["a@example.com"])])

        assert transport.pushed == []

    async def test_middleware_cancellation_prevents_dispatch(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)
        started = asyncio.Event()

        @client.enqueue_middleware
        async def block(request, next_fn):
            started.set()
            await asyncio.Event().wait()
            return await next_fn(request)

        task = asyncio.create_task(client.enqueue("email.send", []))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert transport.pushed == []

    async def test_caller_inputs_are_not_mutated(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)
        args = [{"to": "user@example.com"}]
        meta = {"tenant": {"id": "t1"}}
        original_args = copy.deepcopy(args)
        original_meta = copy.deepcopy(meta)

        @client.enqueue_middleware
        async def mutate(request, next_fn):
            request.args[0]["to"] = "changed@example.com"
            request.meta["tenant"]["id"] = "changed"
            return await next_fn(request)

        await client.enqueue("email.send", args, meta=meta)

        assert args == original_args
        assert meta == original_meta

    async def test_fake_transport_records_encrypted_batch_payloads(self) -> None:
        transport = ExplicitFakeTransport()
        client = ojs.Client("http://unused", transport=transport)
        codec = EncryptionCodec(StaticKeyProvider({"v1": b"k" * 32}, current_key="v1"))
        client.enqueue_middleware(encryption_middleware(codec))

        await client.enqueue_batch([ojs.JobRequest(type="email.send", args=["secret@example.com"])])

        recorded = transport.store.enqueued[0]
        assert recorded.args != ["secret@example.com"]
        assert recorded.meta["ojs.codec.key_id"] == "v1"
        assert recorded.meta["ojs.codec.encodings"] == ["binary/encrypted"]


class TestBatchMiddlewareBarrier:
    """OJS-PY-049: the batch terminal must resolve with the real transport job.

    Before the fix, each batch item's middleware terminal resolved with a
    fabricated placeholder ``Job`` instead of the job the atomic
    ``push_batch`` transport call actually returned. Any middleware code
    that ran *after* calling ``next_fn`` (to observe the result or return a
    transformed value) saw fictitious placeholder data, and transformations
    were silently discarded unless they happened to preserve the
    placeholder's id.
    """

    async def test_post_next_middleware_observes_real_transport_job(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)
        observed: list[ojs.Job] = []

        @client.enqueue_middleware
        async def observe(request: Any, next_fn: Any) -> Any:
            result = await next_fn(request)
            observed.append(result)
            return result

        [job] = await client.enqueue_batch(
            [ojs.JobRequest(type="email.send", args=["a@example.com"])]
        )

        assert len(observed) == 1
        # The observed job must be the SAME real transport-issued job
        # returned to the caller, not a `__ojs_batch_pending_*` placeholder.
        assert observed[0] is job
        assert not job.id.startswith("__ojs_batch_pending_")
        assert job.state == ojs.JobState.AVAILABLE

    async def test_post_next_middleware_transformation_is_applied(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def annotate(request: Any, next_fn: Any) -> Any:
            result = await next_fn(request)
            return dataclasses.replace(result, meta={**result.meta, "annotated": True})

        [job] = await client.enqueue_batch(
            [ojs.JobRequest(type="email.send", args=["a@example.com"])]
        )

        # The transformation is based on the REAL transport job (verified by
        # its non-placeholder id) and its return value is what the caller
        # ultimately receives.
        assert not job.id.startswith("__ojs_batch_pending_")
        assert job.meta["annotated"] is True

    async def test_post_next_none_is_a_silent_drop_not_an_error(
        self,
        transport: FakeTransport,
    ) -> None:
        """A post-next `None` hides the item from results without erroring.

        The job was already durably created by the one atomic transport
        call, so raising would incorrectly imply nothing was enqueued.
        """
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def hide_second(request: Any, next_fn: Any) -> Any:
            result = await next_fn(request)
            if request.args == ["hide-me@example.com"]:
                return None
            return result

        results = await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["a@example.com"]),
                ojs.JobRequest(type="email.send", args=["hide-me@example.com"]),
            ]
        )

        assert len(results) == 1
        assert results[0].args == ["a@example.com"]
        # The hidden job was still sent to the transport as part of the one
        # atomic batch call; only its presence in the *returned* list is
        # suppressed.
        assert len(transport.pushed) == 2
        assert [body["args"] for body in transport.pushed] == [
            ["a@example.com"],
            ["hide-me@example.com"],
        ]

    async def test_replace_middleware_skips_transport_but_others_still_sent(
        self,
        transport: FakeTransport,
    ) -> None:
        """A middleware that never calls next_fn ("replace") isn't sent.

        Other items in the same batch are unaffected and still go through
        the single atomic transport call.
        """
        client = ojs.Client("http://localhost:8080", transport=transport)
        fabricated = ojs.Job(
            id="fabricated-id",
            type="email.send",
            state=ojs.JobState.COMPLETED,
            args=["replaced"],
        )

        @client.enqueue_middleware
        async def replace_first(request: Any, next_fn: Any) -> Any:
            if request.args == ["replace-me@example.com"]:
                return fabricated
            return await next_fn(request)

        results = await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["replace-me@example.com"]),
                ojs.JobRequest(type="email.send", args=["b@example.com"]),
            ]
        )

        assert len(results) == 2
        assert results[0] is fabricated
        assert results[1].args == ["b@example.com"]
        assert not results[1].id.startswith("__ojs_batch_pending_")
        # Only the non-replaced item reaches the transport.
        assert len(transport.pushed) == 1
        assert transport.pushed[0]["args"] == ["b@example.com"]

    async def test_batch_issues_exactly_one_atomic_transport_call(
        self,
        transport: FakeTransport,
    ) -> None:
        call_count = 0
        original_push_batch = transport.push_batch

        async def counting_push_batch(jobs: list[dict[str, Any]]) -> list[ojs.Job]:
            nonlocal call_count
            call_count += 1
            return await original_push_batch(jobs)

        transport.push_batch = counting_push_batch  # type: ignore[method-assign]
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def passthrough(request: Any, next_fn: Any) -> Any:
            return await next_fn(request)

        await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["a@example.com"]),
                ojs.JobRequest(type="email.send", args=["b@example.com"]),
                ojs.JobRequest(type="email.send", args=["c@example.com"]),
            ]
        )

        assert call_count == 1

    async def test_order_preserved_with_mixed_transform_and_drop(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def mixed(request: Any, next_fn: Any) -> Any:
            result = await next_fn(request)
            if request.args == ["drop@example.com"]:
                return None
            if request.args == ["transform@example.com"]:
                return dataclasses.replace(result, meta={**result.meta, "transformed": True})
            return result

        results = await client.enqueue_batch(
            [
                ojs.JobRequest(type="email.send", args=["first@example.com"]),
                ojs.JobRequest(type="email.send", args=["drop@example.com"]),
                ojs.JobRequest(type="email.send", args=["transform@example.com"]),
            ]
        )

        assert [r.args for r in results] == [["first@example.com"], ["transform@example.com"]]
        assert results[1].meta["transformed"] is True
        # All three were still sent atomically to the transport, in order.
        assert len(transport.pushed) == 3

    async def test_pre_terminal_rejection_still_aborts_whole_batch(
        self,
        transport: FakeTransport,
    ) -> None:
        """Retains the existing "reject before terminal" abort semantics."""
        client = ojs.Client("http://localhost:8080", transport=transport)

        @client.enqueue_middleware
        async def reject_second(request: Any, next_fn: Any) -> Any:
            if request.args == ["reject-me@example.com"]:
                return None
            return await next_fn(request)

        with pytest.raises(ojs.OJSError, match="batch item"):
            await client.enqueue_batch(
                [
                    ojs.JobRequest(type="email.send", args=["a@example.com"]),
                    ojs.JobRequest(type="email.send", args=["reject-me@example.com"]),
                ]
            )

        # Nothing reaches the transport: the whole batch is atomic.
        assert transport.pushed == []

    async def test_transport_failure_aborts_whole_batch_and_propagates(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        async def failing_push_batch(jobs: list[dict[str, Any]]) -> list[ojs.Job]:
            raise ojs.OJSConnectionError("transport unavailable")

        transport.push_batch = failing_push_batch  # type: ignore[method-assign]

        observed_errors: list[BaseException] = []

        @client.enqueue_middleware
        async def observe_failure(request: Any, next_fn: Any) -> Any:
            try:
                return await next_fn(request)
            except Exception as exc:
                observed_errors.append(exc)
                raise

        with pytest.raises(ojs.OJSConnectionError, match="transport unavailable"):
            await client.enqueue_batch(
                [
                    ojs.JobRequest(type="email.send", args=["a@example.com"]),
                    ojs.JobRequest(type="email.send", args=["b@example.com"]),
                ]
            )

        # Both chains observe the same transport failure via their
        # post-next code (their terminal futures were rejected with it).
        assert len(observed_errors) == 2
        assert all(isinstance(exc, ojs.OJSConnectionError) for exc in observed_errors)

    async def test_empty_batch_does_not_call_transport(
        self,
        transport: FakeTransport,
    ) -> None:
        client = ojs.Client("http://localhost:8080", transport=transport)

        results = await client.enqueue_batch([])

        assert results == []
        assert transport.pushed == []


class TestJobOperations:
    async def test_get_job(self, client: ojs.Client) -> None:
        job = await client.get_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
        assert job.id == "019539a4-b68c-7def-8000-1a2b3c4d5e6f"
        assert job.state == ojs.JobState.COMPLETED

    async def test_cancel_job(self, client: ojs.Client) -> None:
        job = await client.cancel_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
        assert job.state == ojs.JobState.CANCELLED


class TestWorkflow:
    async def test_create_chain_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.chain(
                "test-chain",
                [
                    ojs.JobRequest(type="step.one", args=["a"]),
                    ojs.JobRequest(type="step.two", args=["b"]),
                ],
            )
        )
        assert wf.name == "test-chain"
        assert wf.state == "running"

    async def test_create_group_workflow(self, client: ojs.Client) -> None:
        wf = await client.workflow(
            ojs.group(
                "test-group",
                [
                    ojs.JobRequest(type="task.a", args=[1]),
                    ojs.JobRequest(type="task.b", args=[2]),
                ],
            )
        )
        assert wf.name == "test-group"


class TestContextManager:
    async def test_async_context_manager(self, transport: FakeTransport) -> None:
        async with ojs.Client("http://localhost:8080", transport=transport) as client:
            job = await client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"

    async def test_health(self, client: ojs.Client) -> None:
        result = await client.health()
        assert result["status"] == "ok"


class TestSyncClient:
    def test_sync_enqueue(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        try:
            job = client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"
        finally:
            client.close()

    def test_sync_get_job(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        try:
            job = client.get_job("019539a4-b68c-7def-8000-1a2b3c4d5e6f")
            assert job.state.value == "completed"
        finally:
            client.close()

    def test_sync_list_queues(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        try:
            queues = client.list_queues()
            assert len(queues) == 1
            assert queues[0].name == "default"
        finally:
            client.close()

    def test_sync_queue_stats(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        try:
            stats = client.queue_stats("default")
            assert stats.queue == "default"
        finally:
            client.close()

    def test_sync_context_manager(self, transport: FakeTransport) -> None:
        with ojs.SyncClient(
            "http://localhost:8080",
            transport=transport,
        ) as client:
            job = client.enqueue("test.echo", ["hello"])
            assert job.type == "test.echo"

    def test_concurrent_threads_are_serialized(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                jobs = list(
                    executor.map(
                        lambda index: client.enqueue("test.echo", [index]),
                        range(8),
                    )
                )
        finally:
            client.close()

        assert [job.args for job in jobs] == [[index] for index in range(8)]
        assert len(transport.pushed) == 8

    def test_close_before_first_call_is_safe(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        client.close()

    def test_close_is_idempotent(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        client.close()
        client.close()

    def test_reuse_after_close_raises(self, transport: FakeTransport) -> None:
        client = ojs.SyncClient("http://localhost:8080", transport=transport)
        client.close()

        with pytest.raises(RuntimeError, match="closed"):
            client.enqueue("test.echo", [])

    def test_worker_operations_with_explicit_fake_transport(self) -> None:
        transport = ExplicitFakeTransport()
        with ojs.SyncClient("http://unused", transport=transport) as client:
            enqueued = client.enqueue("test.echo", ["hello"])
            fetched = client.fetch(["default"])

            assert [job.id for job in fetched] == [enqueued.id]
            assert client.ack(enqueued.id, {"ok": True})["state"] == "completed"
            assert client.get_job(enqueued.id).result == {"ok": True}

            failed = client.enqueue("test.fail", [])
            client.fetch(["default"])
            assert (
                client.nack(
                    failed.id,
                    {"code": "failed", "message": "boom", "retryable": False},
                )["state"]
                == "discarded"
            )
