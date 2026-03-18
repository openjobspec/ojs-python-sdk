"""OJS Replay Studio Recorder.

.. note::

   This module is part of **OJS Labs** — forward-looking R&D that is not
   part of the core release train. APIs may change between minor versions.

Captures execution traces for the Replay Studio, including function
calls, timing, and source map information.

Usage::

    from ojs.recorder import Recorder, RecordingLevel

    recorder = Recorder(level=RecordingLevel.FULL)
    recorder.record_call("process_payment", args={"amount": 100}, result={"ok": True}, duration_ms=42)
    recorder.attach_sourcemap(git_sha="abc123", file_path="src/pay.py", line=15)

    for entry in recorder.trace():
        print(entry)
"""

from ojs.recorder.recorder import (
    Recorder,
    RecordingLevel,
    TraceEntry,
    SourceMap,
)

__all__ = [
    "Recorder",
    "RecordingLevel",
    "TraceEntry",
    "SourceMap",
]
