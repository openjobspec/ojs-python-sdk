"""Incremental SSE field parsing and malformed-data policy."""

from __future__ import annotations

import json
from typing import Literal, TypeAlias, cast

from ojs.errors import OJSValidationError
from ojs.sse.models import SSEEvent

MalformedDataPolicy: TypeAlias = Literal["raise", "raw"]


class SSEDataError(OJSValidationError):
    """An SSE data frame was not a valid OJS JSON object."""


class SSEFrameParser:
    """Incremental parser for one SSE connection's line stream.

    Tracks the "last event ID buffer" per the WHATWG SSE processing model:
    it is seeded from ``initial_event_id`` (the session's current value,
    typically what was last sent as ``Last-Event-ID``), updated whenever an
    ``id`` field is processed, and — critically — is *not* reset between
    dispatched events. This means:

    - A block with no ``id`` field inherits whatever the buffer currently
      holds (from an earlier block in this connection, or from
      ``initial_event_id`` if none has been seen yet this connection).
    - A block with an ``id`` field present but empty (``id`` alone, or
      ``id:`` with no value) explicitly resets the buffer to the empty
      string, distinct from the field being absent entirely.
    """

    def __init__(
        self,
        malformed_data: MalformedDataPolicy = "raw",
        *,
        initial_event_id: str = "",
    ) -> None:
        if malformed_data not in ("raise", "raw"):
            raise ValueError("malformed_data must be 'raise' or 'raw'")
        self._malformed_data = malformed_data
        self._event_type = ""
        self._last_event_id = initial_event_id
        self._data_lines: list[str] = []

    @property
    def last_event_id(self) -> str:
        """The current last-event-ID buffer, including updates from fields
        processed in frames that were discarded (see ``finish()``)."""
        return self._last_event_id

    def feed(self, line: str) -> SSEEvent | None:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None

        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event_type = value
        elif field == "id" and "\x00" not in value:
            # Per the SSE processing model, this sets the last event ID
            # buffer immediately as the field is read — including to the
            # empty string for a present-but-empty `id` field — regardless
            # of whether this frame is ever dispatched. The buffer is
            # intentionally *not* reset elsewhere, so it persists across
            # frames until the next `id` field changes it again.
            self._last_event_id = value
        elif field == "data":
            self._data_lines.append(value)
        return None

    def finish(self) -> SSEEvent | None:
        """Discard a truncated frame that was not terminated by a blank line.

        Only the data and event-type buffers are discarded here; the last
        event ID buffer is untouched (any ``id`` field already seen in the
        truncated frame already updated it via ``feed()``, and per spec the
        last event ID buffer is never reset on dispatch or discard).
        """
        self._event_type = ""
        self._data_lines = []
        return None

    def _dispatch(self) -> SSEEvent | None:
        raw = "\n".join(self._data_lines)
        event_type = self._event_type or "message"
        event_id = self._last_event_id
        self._event_type = ""
        self._data_lines = []
        if not raw:
            return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            if self._malformed_data == "raw":
                return SSEEvent(id=event_id, type=event_type, data=None, raw=raw)
            raise SSEDataError("SSE data is not valid JSON") from exc
        if not isinstance(payload, dict):
            if self._malformed_data == "raw":
                return SSEEvent(id=event_id, type=event_type, data=None, raw=raw)
            raise SSEDataError("SSE data must be a JSON object")
        return SSEEvent(
            id=event_id,
            type=event_type,
            data=cast(dict[str, object], payload),
            raw=raw,
        )


__all__ = ["MalformedDataPolicy", "SSEDataError", "SSEFrameParser"]
