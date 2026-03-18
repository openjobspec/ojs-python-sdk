"""OJS Python SDK Recorder — captures execution traces for job handlers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SourceMap:
    """Maps a trace entry to its source code location."""
    git_sha: str
    file_path: str
    line: int


@dataclass
class TraceEntry:
    """A single recorded function call."""
    func_name: str
    args: str
    result: str
    duration_ms: int
    source_map: SourceMap | None = None
    timestamp: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class Recorder:
    """Captures execution traces for a single job handler invocation.

    Example::

        recorder = Recorder()
        start = time.monotonic()
        result = handler(args)
        elapsed = int((time.monotonic() - start) * 1000)
        recorder.record_call("handler", args, result, elapsed)
        recorder.attach_source_map("abc123", "handler.py", 42)
        print(recorder.trace())
    """

    def __init__(self) -> None:
        self._entries: list[TraceEntry] = []

    def record_call(
        self, func_name: str, args: Any, result: Any, duration_ms: int
    ) -> None:
        """Record a successful function call."""
        self._entries.append(
            TraceEntry(
                func_name=func_name,
                args=_serialize(args),
                result=_serialize(result),
                duration_ms=duration_ms,
            )
        )

    def record_error(
        self, func_name: str, args: Any, error: BaseException | str, duration_ms: int
    ) -> None:
        """Record a failed function call."""
        err_msg = str(error) if isinstance(error, BaseException) else error
        self._entries.append(
            TraceEntry(
                func_name=func_name,
                args=_serialize(args),
                result="",
                duration_ms=duration_ms,
                error=err_msg,
            )
        )

    def attach_source_map(self, git_sha: str, file_path: str, line: int) -> None:
        """Attach source location to the most recent trace entry."""
        if not self._entries:
            return
        self._entries[-1].source_map = SourceMap(
            git_sha=git_sha, file_path=file_path, line=line
        )

    def trace(self) -> list[TraceEntry]:
        """Return a copy of all recorded trace entries."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def reset(self) -> None:
        """Clear all recorded entries."""
        self._entries.clear()

    def to_json(self) -> str:
        """Export the trace as a JSON string."""
        return json.dumps(
            [
                {
                    "func_name": e.func_name,
                    "args": e.args,
                    "result": e.result,
                    "duration_ms": e.duration_ms,
                    "source_map": (
                        {
                            "git_sha": e.source_map.git_sha,
                            "file_path": e.source_map.file_path,
                            "line": e.source_map.line,
                        }
                        if e.source_map
                        else None
                    ),
                    "timestamp": e.timestamp,
                    "error": e.error,
                }
                for e in self._entries
            ]
        )


def _serialize(obj: Any) -> str:
    """Serialize an object to JSON string."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return str(obj)
