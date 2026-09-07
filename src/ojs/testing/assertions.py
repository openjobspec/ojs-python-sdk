"""OJS Testing Module — fake mode, assertions, and test utilities.

Implements the OJS Testing Specification (ojs-testing.md).

Usage::

    import pytest
    from ojs.testing import fake_mode, assert_enqueued, refute_enqueued, drain

    @pytest.fixture(autouse=True)
    def ojs_testing():
        with fake_mode():
            yield

    async def test_sends_welcome_email():
        await signup_user(email="user@example.com")
        assert_enqueued("email.send", args=[{"to": "user@example.com"}])
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ojs.transport.fake import (
    FakeJob,
    FakeStore,
    FakeTransport,
    activate_fake_transport,
    current_fake_transport,
)


def _get_store(
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> FakeStore:
    if store is not None:
        return store
    if transport is not None:
        return transport.store
    active = current_fake_transport()
    if active is None:
        raise RuntimeError("OJS testing: not in fake mode. Use `with fake_mode():` first.")
    return active.store


@contextmanager
def fake_mode(
    transport: FakeTransport | None = None,
) -> Iterator[FakeStore]:
    """Context manager that activates fake mode.

    Usage::

        with fake_mode() as store:
            client.enqueue("email.send", [{"to": "user@example.com"}])
            assert_enqueued("email.send")
    """
    selected = transport or FakeTransport()
    with activate_fake_transport(selected):
        yield selected.store


def is_fake_mode() -> bool:
    """Return True if fake mode is active."""
    return current_fake_transport() is not None


def get_store() -> FakeStore | None:
    """Return the active fake store, or None."""
    active = current_fake_transport()
    return active.store if active is not None else None


def assert_enqueued(
    job_type: str,
    *,
    args: list[Any] | None = None,
    queue: str | None = None,
    meta: dict[str, Any] | None = None,
    count: int | None = None,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Assert that at least one job of the given type was enqueued."""
    selected = _get_store(store, transport)
    matches = _find_matching(
        selected.enqueued,
        job_type,
        args=args,
        queue=queue,
        meta=meta,
    )

    if count is not None:
        if len(matches) != count:
            enqueued_types = {j.type for j in selected.enqueued}
            raise AssertionError(
                f"Expected {count} enqueued job(s) of type '{job_type}', found {len(matches)}. "
                f"Enqueued types: {enqueued_types}"
            )
    elif len(matches) == 0:
        enqueued_types = {j.type for j in selected.enqueued}
        raise AssertionError(
            f"Expected at least one enqueued job of type '{job_type}', found none. "
            f"Enqueued types: {enqueued_types or 'none'}"
        )


def refute_enqueued(
    job_type: str,
    *,
    args: list[Any] | None = None,
    queue: str | None = None,
    meta: dict[str, Any] | None = None,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Assert that NO job of the given type was enqueued."""
    selected = _get_store(store, transport)
    matches = _find_matching(
        selected.enqueued,
        job_type,
        args=args,
        queue=queue,
        meta=meta,
    )
    if matches:
        raise AssertionError(
            f"Expected no enqueued jobs of type '{job_type}', but found {len(matches)}."
        )


def assert_performed(
    job_type: str,
    *,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Assert that at least one job of the given type was performed."""
    selected = _get_store(store, transport)
    matches = [j for j in selected.performed if j.type == job_type]
    if not matches:
        raise AssertionError(
            f"Expected at least one performed job of type '{job_type}', found none."
        )


def assert_completed(
    job_type: str,
    *,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Assert that at least one job of the given type completed successfully."""
    selected = _get_store(store, transport)
    match = next(
        (job for job in selected.performed if job.type == job_type and job.state == "completed"),
        None,
    )
    if not match:
        raise AssertionError(f"Expected a completed job of type '{job_type}', found none.")


def assert_failed(
    job_type: str,
    *,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Assert that at least one job of the given type failed."""
    selected = _get_store(store, transport)
    match = next(
        (job for job in selected.performed if job.type == job_type and job.state == "discarded"),
        None,
    )
    if not match:
        raise AssertionError(f"Expected a failed job of type '{job_type}', found none.")


def all_enqueued(
    job_type: str | None = None,
    queue: str | None = None,
    *,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> list[FakeJob]:
    """Return all enqueued jobs, optionally filtered."""
    jobs = _get_store(store, transport).enqueued
    if job_type:
        jobs = [j for j in jobs if j.type == job_type]
    if queue:
        jobs = [j for j in jobs if j.queue == queue]
    return list(jobs)


def clear_all(
    *,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> None:
    """Clear all enqueued and performed jobs."""
    _get_store(store, transport).clear()


def drain(
    *,
    max_jobs: int | None = None,
    store: FakeStore | None = None,
    transport: FakeTransport | None = None,
) -> int:
    """Process all available enqueued jobs using registered handlers.

    Returns the number of jobs processed.
    """
    selected = _get_store(store, transport)
    processed = 0
    limit = max_jobs or len(selected.enqueued)

    for job in selected.enqueued:
        if processed >= limit:
            break
        if job.state != "available":
            continue

        job.state = "active"
        job.attempt += 1
        handler = selected.handlers.get(job.type)

        if handler:
            try:
                handler(job)
                job.state = "completed"
            except Exception:
                job.state = "discarded"
        else:
            job.state = "completed"

        selected.performed.append(job)
        processed += 1

    return processed


def _find_matching(
    jobs: list[FakeJob],
    job_type: str,
    args: list[Any] | None = None,
    queue: str | None = None,
    meta: dict[str, Any] | None = None,
) -> list[FakeJob]:
    result = []
    for j in jobs:
        if j.type != job_type:
            continue
        if queue and j.queue != queue:
            continue
        if args is not None and j.args != args:
            continue
        if meta and not all(j.meta.get(k) == v for k, v in meta.items()):
            continue
        result.append(j)
    return result
