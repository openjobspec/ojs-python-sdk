"""Process-signal ownership for worker runtimes."""

from __future__ import annotations

import asyncio
import signal
import threading
from collections.abc import Callable
from types import FrameType
from typing import TypeAlias

SignalHandler: TypeAlias = Callable[[int, FrameType | None], object] | int | signal.Handlers | None


class SignalCustodian:
    """Install one worker's handlers and restore the process handlers afterward."""

    _owner_lock = threading.Lock()
    _owner: SignalCustodian | None = None

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled
        self._loop: asyncio.AbstractEventLoop | None = None
        self._previous: dict[signal.Signals, SignalHandler] = {}
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    def install(self, callback: Callable[[], None]) -> bool:
        if not self._enabled:
            return False
        if threading.current_thread() is not threading.main_thread():
            return False

        loop = asyncio.get_running_loop()
        with self._owner_lock:
            if self.__class__._owner not in (None, self):
                raise RuntimeError("another worker owns the process signal handlers")
            self.__class__._owner = self

        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                self._previous[signum] = signal.getsignal(signum)
                loop.add_signal_handler(signum, callback)
        except (NotImplementedError, RuntimeError):
            self._restore_owner()
            self._previous.clear()
            return False

        self._loop = loop
        self._installed = True
        return True

    def restore(self) -> None:
        if not self._installed:
            self._restore_owner()
            return

        if self._loop is None:
            raise RuntimeError("installed signal custodian has no event loop")
        for signum, previous in self._previous.items():
            self._loop.remove_signal_handler(signum)
            signal.signal(signum, previous)
        self._previous.clear()
        self._loop = None
        self._installed = False
        self._restore_owner()

    def _restore_owner(self) -> None:
        with self._owner_lock:
            if self.__class__._owner is self:
                self.__class__._owner = None


__all__ = ["SignalCustodian", "SignalHandler"]
