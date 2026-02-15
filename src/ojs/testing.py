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

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class FakeJob:
    """A job recorded in fake mode."""

    id: str
    type: str
    queue: str
    args: list[Any]
    meta: dict[str, Any]
    state: str = "available"
    attempt: int = 0
    options: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()


class FakeStore:
    """In-memory store for fake mode."""

    def __init__(self) -> None:
        self.enqueued: list[FakeJob] = []
        self.performed: list[FakeJob] = []
        self.handlers: dict[str, Callable[[FakeJob], None]] = {}
        self._next_id = 0

    def record_enqueue(
        self,
        job_type: str,
        args: list[Any],
        queue: str = "default",
        meta: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> FakeJob:
        self._next_id += 1
        job = FakeJob(
            id=f"fake-{self._next_id:06d}",
            type=job_type,
            queue=queue,
            args=args,
            meta=meta or {},
            options=options or {},
        )
        self.enqueued.append(job)
        return job

    def register_handler(self, job_type: str, handler: Callable[[FakeJob], None]) -> None:
        self.handlers[job_type] = handler

    def clear(self) -> None:
        self.enqueued.clear()
        self.performed.clear()


# Global state
_active_store: FakeStore | None = None


def _get_store() -> FakeStore:
    if _active_store is None:
        raise RuntimeError("OJS testing: not in fake mode. Use `with fake_mode():` first.")
    return _active_store


@contextmanager
def fake_mode() -> Generator[FakeStore, None, None]:
    """Context manager that activates fake mode.

    Usage::

        with fake_mode() as store:
            client.enqueue("email.send", [{"to": "user@example.com"}])
            assert_enqueued("email.send")
    """
    global _active_store
    store = FakeStore()
    _active_store = store
    try:
        yield store
    finally:
        _active_store = None


def is_fake_mode() -> bool:
    """Return True if fake mode is active."""
    return _active_store is not None


def get_store() -> FakeStore | None:
    """Return the active fake store, or None."""
    return _active_store


def assert_enqueued(
    job_type: str,
    *,
    args: list[Any] | None = None,
    queue: str | None = None,
    meta: dict[str, Any] | None = None,
    count: int | None = None,
) -> None:
    """Assert that at least one job of the given type was enqueued."""
    store = _get_store()
    matches = _find_matching(store.enqueued, job_type, args=args, queue=queue, meta=meta)

    if count is not None:
        if len(matches) != count:
            enqueued_types = {j.type for j in store.enqueued}
            raise AssertionError(
                f"Expected {count} enqueued job(s) of type '{job_type}', found {len(matches)}. "
                f"Enqueued types: {enqueued_types}"
            )
    elif len(matches) == 0:
        enqueued_types = {j.type for j in store.enqueued}
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
) -> None:
    """Assert that NO job of the given type was enqueued."""
    store = _get_store()
    matches = _find_matching(store.enqueued, job_type, args=args, queue=queue, meta=meta)
    if matches:
        raise AssertionError(
            f"Expected no enqueued jobs of type '{job_type}', but found {len(matches)}."
        )


def assert_performed(job_type: str) -> None:
    """Assert that at least one job of the given type was performed."""
    store = _get_store()
    matches = [j for j in store.performed if j.type == job_type]
    if not matches:
        raise AssertionError(
            f"Expected at least one performed job of type '{job_type}', found none."
        )


def assert_completed(job_type: str) -> None:
    """Assert that at least one job of the given type completed successfully."""
    store = _get_store()
    match = next(
        (j for j in store.performed if j.type == job_type and j.state == "completed"), None
    )
    if not match:
        raise AssertionError(f"Expected a completed job of type '{job_type}', found none.")


def assert_failed(job_type: str) -> None:
    """Assert that at least one job of the given type failed."""
    store = _get_store()
    match = next(
        (j for j in store.performed if j.type == job_type and j.state == "discarded"), None
    )
    if not match:
        raise AssertionError(f"Expected a failed job of type '{job_type}', found none.")


def all_enqueued(job_type: str | None = None, queue: str | None = None) -> list[FakeJob]:
    """Return all enqueued jobs, optionally filtered."""
    store = _get_store()
    jobs = store.enqueued
    if job_type:
        jobs = [j for j in jobs if j.type == job_type]
    if queue:
        jobs = [j for j in jobs if j.queue == queue]
    return list(jobs)


def clear_all() -> None:
    """Clear all enqueued and performed jobs."""
    _get_store().clear()


def drain(*, max_jobs: int | None = None) -> int:
    """Process all available enqueued jobs using registered handlers.

    Returns the number of jobs processed.
    """
    store = _get_store()
    processed = 0
    limit = max_jobs or len(store.enqueued)

    for job in store.enqueued:
        if processed >= limit:
            break
        if job.state != "available":
            continue

        job.state = "active"
        job.attempt += 1
        handler = store.handlers.get(job.type)

        if handler:
            try:
                handler(job)
                job.state = "completed"
            except Exception:
                job.state = "discarded"
        else:
            job.state = "completed"

        store.performed.append(job)
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
