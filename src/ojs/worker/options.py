"""Validation and normalization of worker runtime options."""

from __future__ import annotations

from math import isfinite


def validate_worker_options(
    *,
    concurrency: int,
    poll_interval: float,
    heartbeat_interval: float,
    visibility_timeout_ms: int | None,
    visibility_timeout: float | None,
    request_timeout: float,
    grace_period: float,
) -> int:
    """Validate worker timings and return visibility timeout in milliseconds."""
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    _positive_number("poll_interval", poll_interval)
    _positive_number("heartbeat_interval", heartbeat_interval)
    _positive_number("timeout", request_timeout)
    _non_negative_number("grace_period", grace_period)

    if visibility_timeout is not None and visibility_timeout_ms is not None:
        raise ValueError("visibility_timeout and visibility_timeout_ms are mutually exclusive")
    if visibility_timeout is not None:
        _positive_number("visibility_timeout", visibility_timeout)
        resolved = int(visibility_timeout * 1000)
        if resolved < 1:
            raise ValueError("visibility_timeout must resolve to at least 1 millisecond")
        return resolved
    if visibility_timeout_ms is None:
        return 30000
    if (
        not isinstance(visibility_timeout_ms, int)
        or isinstance(visibility_timeout_ms, bool)
        or visibility_timeout_ms < 1
    ):
        raise ValueError("visibility_timeout_ms must be a positive integer")
    return visibility_timeout_ms


def _positive_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _non_negative_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a non-negative finite number")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative finite number")


__all__ = ["validate_worker_options"]
