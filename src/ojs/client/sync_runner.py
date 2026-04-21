"""Dedicated event-loop thread for the synchronous client facade."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class SyncRunner:
    """Serialize coroutine submission onto one owned event-loop thread."""

    def __init__(self, *, thread_name: str = "ojs-sync-client") -> None:
        self._thread_name = thread_name
        self._state_lock = threading.Lock()
        self._submission_lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    def run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        """Run a coroutine on the owned loop and return its result."""
        with self._submission_lock:
            try:
                loop = self._ensure_loop()
            except BaseException:
                coroutine.close()
                raise
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            return future.result()

    def close(self, coroutine: Coroutine[Any, Any, None]) -> None:
        """Run final async cleanup, stop the loop, and join its thread."""
        with self._submission_lock:
            with self._state_lock:
                if self._closed:
                    coroutine.close()
                    return
                loop = self._start_loop_locked()
                thread = self._thread

            cleanup_error: BaseException | None = None
            try:
                asyncio.run_coroutine_threadsafe(coroutine, loop).result()
            except BaseException as exc:
                cleanup_error = exc
            finally:
                with self._state_lock:
                    self._closed = True
                loop.call_soon_threadsafe(loop.stop)
                if thread is not None:
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        raise RuntimeError("SyncClient event-loop thread did not stop")
            if cleanup_error is not None:
                raise cleanup_error

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("SyncClient is closed")
            return self._start_loop_locked()

    def _start_loop_locked(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=self._thread_name,
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("SyncClient event-loop thread failed to start")
        if self._loop is None:
            raise RuntimeError("SyncClient event loop was not initialized")
        return self._loop

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()


__all__ = ["SyncRunner"]
