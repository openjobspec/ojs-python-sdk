"""Explicit worker loop cancellation and graceful execution draining."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from ojs.worker.run_state import WorkerRunState


class ShutdownCoordinator:
    """Coordinate loop ownership without relying on sibling task cancellation."""

    def __init__(self, run_state: WorkerRunState, grace_period: float) -> None:
        self._run_state = run_state
        self._grace_period = grace_period

    async def run(
        self,
        fetch_loop: Coroutine[object, object, None],
        heartbeat_loop: Coroutine[object, object, None],
    ) -> None:
        fetch_task = asyncio.create_task(fetch_loop, name="ojs-worker-fetch")
        heartbeat_task = asyncio.create_task(
            heartbeat_loop,
            name="ojs-worker-heartbeat",
        )
        shutdown_task = asyncio.create_task(
            self._run_state.shutdown.wait(),
            name="ojs-worker-shutdown",
        )
        loop_tasks = (fetch_task, heartbeat_task)
        failure: BaseException | None = None

        try:
            done, _ = await asyncio.wait(
                (*loop_tasks, shutdown_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if task is shutdown_task or task.cancelled():
                    continue
                error = task.exception()
                if error is not None:
                    failure = error
                    break
        finally:
            self._run_state.request_shutdown()
            for task in loop_tasks:
                if not task.done():
                    task.cancel()
            shutdown_task.cancel()
            await asyncio.gather(*loop_tasks, shutdown_task, return_exceptions=True)
            await self._drain_executions()

        if failure is not None:
            raise failure

    async def _drain_executions(self) -> None:
        try:
            await asyncio.wait_for(
                self._run_state.executions.wait_empty(),
                timeout=self._grace_period,
            )
            return
        except TimeoutError:
            pass

        active_tasks = self._run_state.executions.active_tasks()
        for task in active_tasks:
            task.cancel()
        await asyncio.gather(*active_tasks, return_exceptions=True)
        await self._run_state.executions.wait_empty()


__all__ = ["ShutdownCoordinator"]
