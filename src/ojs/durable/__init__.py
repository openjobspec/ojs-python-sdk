"""Durable execution facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from ojs.durable.context import DurableContext
from ojs.durable.replay_loader import (
    DurableReplayError,
    ReplayLogEntry,
)


class _SideEffectEntry(ReplayLogEntry):
    __slots__ = ()

    def __init__(
        self,
        seq: int,
        effect_type: str,
        result: object,
        key: str = "",
    ) -> None:
        super().__init__(seq=seq, type=effect_type, result=result, key=key)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> _SideEffectEntry:
        entry = ReplayLogEntry.from_dict(data)
        return cls(
            seq=entry.seq,
            effect_type=entry.type,
            result=entry.result,
            key=entry.key,
        )


T = TypeVar("T")
BASE_PATH = "/ojs/v1"

__all__ = ["BASE_PATH", "DurableContext", "DurableReplayError", "T"]
