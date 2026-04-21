"""SSE event model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SSEEvent:
    """A parsed OJS Server-Sent Event."""

    id: str = ""
    type: str = "message"
    data: dict[str, Any] | None = None
    raw: str = ""


__all__ = ["SSEEvent"]
