"""Bounded lease admission for worker fetches."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LeasePermit:
    """One reserved worker execution slot."""

    token: str


class LeaseAdmission:
    """Reserve execution capacity before asking the backend for leases."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._semaphore = asyncio.BoundedSemaphore(capacity)
        self._permits: dict[str, LeasePermit] = {}

    @property
    def available(self) -> int:
        return self._capacity - len(self._permits)

    @property
    def active(self) -> int:
        return len(self._permits)

    async def reserve_available(self) -> tuple[LeasePermit, ...]:
        """Atomically reserve all capacity currently available to a fetch."""
        permits: list[LeasePermit] = []
        for _ in range(self.available):
            await self._semaphore.acquire()
            permit = LeasePermit(token=str(uuid.uuid4()))
            self._permits[permit.token] = permit
            permits.append(permit)
        return tuple(permits)

    def release(self, permit: LeasePermit) -> bool:
        """Release a permit once; return false for an already released permit."""
        if self._permits.pop(permit.token, None) is None:
            return False
        self._semaphore.release()
        return True


__all__ = ["LeaseAdmission", "LeasePermit"]
