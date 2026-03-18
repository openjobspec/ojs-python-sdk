"""Execution trace recorder for the OJS Replay Studio (M6)."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class RecordingLevel(enum.Enum):
    """Controls the verbosity of recorded traces."""

    FULL = "full"
    SUMMARY = "summary"
    OFF = "off"


@dataclass(frozen=True)
class SourceMap:
    """Links a trace entry to source code via git coordinates."""

    git_sha: str
    file_path: str
    line: int


@dataclass(frozen=True)
class TraceEntry:
    """A single recorded function call or event."""

    func_name: str
    args: Any
    result: Any
    duration_ms: int
    timestamp: datetime
    source_map: SourceMap | None = None


class Recorder:
    """Captures execution traces for the Replay Studio (M6).

    Records function calls with arguments, results, and timing. Optionally
    attaches source maps for linking traces back to source code.

    The recorder respects the configured :class:`RecordingLevel`:

    - ``FULL``: records all calls with args and results.
    - ``SUMMARY``: records call names and timing only (args/results omitted).
    - ``OFF``: no recording (all methods are no-ops).
    """

    def __init__(self, level: RecordingLevel = RecordingLevel.FULL) -> None:
        self._level = level
        self._entries: list[TraceEntry] = []
        self._pending_sourcemap: SourceMap | None = None

    @property
    def level(self) -> RecordingLevel:
        """Current recording level."""
        return self._level

    def record_call(
        self,
        func_name: str,
        args: Any,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Record a function call.

        Args:
            func_name: Name of the function that was called.
            args: Arguments passed to the function.
            result: Return value of the function.
            duration_ms: Wall-clock duration in milliseconds.
        """
        if self._level == RecordingLevel.OFF:
            return

        if self._level == RecordingLevel.SUMMARY:
            args = None
            result = None

        entry = TraceEntry(
            func_name=func_name,
            args=args,
            result=result,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            source_map=self._pending_sourcemap,
        )
        self._entries.append(entry)
        self._pending_sourcemap = None

    def attach_sourcemap(
        self,
        git_sha: str,
        file_path: str,
        line: int,
    ) -> None:
        """Attach source map info to the next recorded call.

        Args:
            git_sha: Git commit SHA of the source.
            file_path: Path to the source file.
            line: Line number in the source file.
        """
        if self._level == RecordingLevel.OFF:
            return

        self._pending_sourcemap = SourceMap(
            git_sha=git_sha,
            file_path=file_path,
            line=line,
        )

    def trace(self) -> list[TraceEntry]:
        """Return all recorded trace entries."""
        return list(self._entries)

    def clear(self) -> None:
        """Clear all recorded entries."""
        self._entries.clear()
        self._pending_sourcemap = None

    def __len__(self) -> int:
        return len(self._entries)
