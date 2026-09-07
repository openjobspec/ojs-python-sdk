"""Adapt offset-based SDK pagination to cursor-based gRPC endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ojs.errors import OJSValidationError

PageFetcher = Callable[[int, str], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class OffsetPage:
    items: list[Any]
    total: int
    next_cursor: str


async def collect_offset_page(
    fetch_page: PageFetcher,
    *,
    items_key: str,
    limit: int,
    offset: int,
) -> OffsetPage:
    """Collect one offset page while following opaque backend cursors."""
    if limit < 1:
        raise OJSValidationError("pagination limit must be at least 1")
    if offset < 0:
        raise OJSValidationError("pagination offset cannot be negative")

    remaining_skip = offset
    collected: list[Any] = []
    cursor = ""
    next_cursor = ""
    total = 0
    seen_cursors: set[str] = set()

    while len(collected) < limit:
        requested = remaining_skip + (limit - len(collected))
        response = await fetch_page(requested, cursor)
        raw_items = response.get(items_key, [])
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raise OJSValidationError(f"gRPC {items_key} response must be an array")
        page_items = list(raw_items)

        raw_total = response.get("total_count", total)
        if isinstance(raw_total, (int, str)):
            try:
                total = int(raw_total)
            except ValueError:
                raise OJSValidationError("gRPC total_count response must be an integer") from None
        raw_next = response.get("next_cursor", "")
        next_cursor = raw_next if isinstance(raw_next, str) else ""

        skipped = min(remaining_skip, len(page_items))
        remaining_skip -= skipped
        page_items = page_items[skipped:]
        collected.extend(page_items[: limit - len(collected)])

        if len(collected) >= limit or not next_cursor:
            break
        if next_cursor in seen_cursors:
            raise OJSValidationError("gRPC pagination returned a repeated cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return OffsetPage(
        items=collected,
        total=total,
        next_cursor=next_cursor,
    )


def slice_offset_page(
    items: Sequence[Any],
    *,
    limit: int,
    offset: int,
) -> OffsetPage:
    """Apply offset semantics to an unpaginated protobuf response."""
    if limit < 1:
        raise OJSValidationError("pagination limit must be at least 1")
    if offset < 0:
        raise OJSValidationError("pagination offset cannot be negative")
    return OffsetPage(
        items=list(items[offset : offset + limit]),
        total=len(items),
        next_cursor="",
    )


__all__ = ["OffsetPage", "collect_offset_page", "slice_offset_page"]
