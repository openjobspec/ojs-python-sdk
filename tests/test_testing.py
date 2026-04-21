"""Tests for OJS testing module (fake mode and assertions)."""

from __future__ import annotations

import asyncio
import inspect

import pytest

import ojs
import ojs.client.async_client
from ojs.testing import (
    all_enqueued,
    assert_completed,
    assert_enqueued,
    assert_failed,
    assert_performed,
    clear_all,
    drain,
    fake_mode,
    is_fake_mode,
    refute_enqueued,
)
from ojs.transport.fake import FakeTransport


class TestFakeMode:
    def test_fake_mode_activates(self) -> None:
        assert not is_fake_mode()
        with fake_mode():
            assert is_fake_mode()
        assert not is_fake_mode()

    def test_fake_mode_yields_store(self) -> None:
        with fake_mode() as store:
            assert store is not None
            assert store.enqueued == []

    def test_nested_fake_mode_restores_outer_store(self) -> None:
        with fake_mode() as outer:
            outer.record_enqueue("outer.job", [])
            with fake_mode() as inner:
                inner.record_enqueue("inner.job", [])
                assert [job.type for job in all_enqueued()] == ["inner.job"]
            assert [job.type for job in all_enqueued()] == ["outer.job"]


class TestFakeModeClientIntegration:
    async def test_existing_implicit_client_observes_active_fake_mode(self) -> None:
        client = ojs.Client("http://unused")
        try:
            with fake_mode():
                job = await client.enqueue("email.send", ["created-before-mode"])
                assert job.id.startswith("fake-")
                assert_enqueued("email.send", args=["created-before-mode"])
        finally:
            await client.close()

    async def test_enqueue_records_in_fake_mode(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                job = await client.enqueue("email.send", ["user@example.com", "welcome"])

            assert job.type == "email.send"
            assert job.args == ["user@example.com", "welcome"]
            assert job.state == ojs.JobState.AVAILABLE
            assert job.id.startswith("fake-")
            assert_enqueued("email.send")

    async def test_enqueue_with_queue(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                job = await client.enqueue("email.send", ["a@b.com"], queue="email")

            assert job.queue == "email"
            assert_enqueued("email.send", queue="email")

    async def test_enqueue_with_meta(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                await client.enqueue(
                    "email.send",
                    ["a@b.com"],
                    meta={"trace_id": "abc"},
                )

            assert_enqueued("email.send", meta={"trace_id": "abc"})

    async def test_enqueue_batch_records_in_fake_mode(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                jobs = await client.enqueue_batch(
                    [
                        ojs.JobRequest(type="email.send", args=["a@b.com"]),
                        ojs.JobRequest(type="email.send", args=["c@d.com"]),
                    ]
                )

            assert len(jobs) == 2
            assert all(j.id.startswith("fake-") for j in jobs)
            assert_enqueued("email.send", count=2)

    async def test_refute_enqueued(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                await client.enqueue("email.send", ["a@b.com"])

            refute_enqueued("sms.send")

    async def test_assert_enqueued_with_args(self) -> None:
        with fake_mode():
            async with ojs.Client("http://fake:8080") as client:
                await client.enqueue("email.send", ["user@example.com"])

            assert_enqueued("email.send", args=["user@example.com"])
            with pytest.raises(AssertionError):
                assert_enqueued("email.send", args=["wrong@example.com"])

    async def test_parallel_explicit_fake_transports_are_isolated(self) -> None:
        first = FakeTransport()
        second = FakeTransport()

        async def enqueue(transport: FakeTransport, address: str) -> None:
            client = ojs.Client("http://unused", transport=transport)
            await client.enqueue("email.send", [address])

        await asyncio.gather(
            enqueue(first, "first@example.com"),
            enqueue(second, "second@example.com"),
        )

        assert first.store.enqueued[0].args == ["first@example.com"]
        assert second.store.enqueued[0].args == ["second@example.com"]
        assert_enqueued("email.send", transport=first)
        assert_enqueued("email.send", transport=second)

    def test_client_does_not_import_testing_module(self) -> None:
        source = inspect.getsource(ojs.client.async_client)
        assert "ojs.testing" not in source


class TestAssertionErrors:
    def test_assert_enqueued_fails_when_none(self) -> None:
        with fake_mode(), pytest.raises(AssertionError, match="found none"):
            assert_enqueued("email.send")

    def test_assert_enqueued_count_mismatch(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a@b.com"])
            with pytest.raises(AssertionError, match="Expected 2"):
                assert_enqueued("email.send", count=2)

    def test_refute_enqueued_fails_when_found(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a@b.com"])
            with pytest.raises(AssertionError, match="found 1"):
                refute_enqueued("email.send")

    def test_assert_outside_fake_mode_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not in fake mode"):
            assert_enqueued("email.send")


class TestAllEnqueued:
    def test_all_enqueued_filter_by_type(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a"])
            store.record_enqueue("sms.send", ["b"])
            store.record_enqueue("email.send", ["c"])

            assert len(all_enqueued("email.send")) == 2
            assert len(all_enqueued("sms.send")) == 1
            assert len(all_enqueued()) == 3

    def test_all_enqueued_filter_by_queue(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("a", [], queue="email")
            store.record_enqueue("b", [], queue="default")

            assert len(all_enqueued(queue="email")) == 1


class TestClearAll:
    def test_clear_all_resets_store(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a"])
            assert len(all_enqueued()) == 1
            clear_all()
            assert len(all_enqueued()) == 0


class TestDrain:
    def test_drain_processes_jobs(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a"])
            store.record_enqueue("email.send", ["b"])
            processed = drain()
            assert processed == 2
            assert_performed("email.send")
            assert_completed("email.send")

    def test_drain_with_handler(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a"])

            def handler(job):
                pass

            store.register_handler("email.send", handler)
            processed = drain()
            assert processed == 1
            assert_completed("email.send")

    def test_drain_with_failing_handler(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("email.send", ["a"])

            def handler(job):
                raise ValueError("boom")

            store.register_handler("email.send", handler)
            drain()
            assert_failed("email.send")

    def test_drain_max_jobs(self) -> None:
        with fake_mode() as store:
            store.record_enqueue("a", [])
            store.record_enqueue("b", [])
            store.record_enqueue("c", [])
            processed = drain(max_jobs=2)
            assert processed == 2
