"""OJS retry policy types and backoff computation.

Implements the retry policy as defined in the OJS Retry Specification,
including exponential backoff with jitter.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any


def _parse_iso8601_duration(duration: str) -> float:
    """Parse an ISO 8601 duration string into seconds.

    Supports the subset used by OJS: PnDTnHnMnS (no years or months).

    Examples:
        >>> _parse_iso8601_duration("PT1S")
        1.0
        >>> _parse_iso8601_duration("PT5M")
        300.0
        >>> _parse_iso8601_duration("PT1H30M")
        5400.0
        >>> _parse_iso8601_duration("P1DT12H")
        129600.0
    """
    pattern = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")
    match = pattern.match(duration)
    if not match:
        raise ValueError(f"Invalid ISO 8601 duration: {duration!r}")

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = float(match.group(4) or 0)

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _seconds_to_iso8601(seconds: float) -> str:
    """Convert seconds to an ISO 8601 duration string."""
    if seconds <= 0:
        return "PT0S"

    parts: list[str] = ["PT"]
    remaining = seconds

    hours = int(remaining // 3600)
    if hours:
        parts.append(f"{hours}H")
        remaining -= hours * 3600

    minutes = int(remaining // 60)
    if minutes:
        parts.append(f"{minutes}M")
        remaining -= minutes * 60

    if remaining > 0 or len(parts) == 1:
        if remaining == int(remaining):
            parts.append(f"{int(remaining)}S")
        else:
            parts.append(f"{remaining:.3f}S")

    return "".join(parts)


@dataclass(frozen=True)
class RetryPolicy:
    """OJS retry policy configuration.

    Attributes:
        max_attempts: Total attempts including the initial execution. Default: 3.
        initial_interval: ISO 8601 duration before the first retry. Default: "PT1S".
        backoff_coefficient: Multiplier applied after each retry. Default: 2.0.
        max_interval: ISO 8601 duration cap on retry delay. Default: "PT5M".
        jitter: Whether to randomize delay to prevent thundering herd. Default: True.
        non_retryable_errors: Error type strings that must not trigger retry.
    """

    max_attempts: int = 3
    initial_interval: str = "PT1S"
    backoff_coefficient: float = 2.0
    max_interval: str = "PT5M"
    jitter: bool = True
    non_retryable_errors: list[str] = field(default_factory=list)

    def delay_for_attempt(self, attempt: int) -> float:
        """Compute the retry delay in seconds for a given attempt number.

        Uses exponential backoff: delay = initial_interval * (backoff_coefficient ** (attempt - 1)).
        If jitter is enabled, the delay is randomized to [0.5 * delay, 1.5 * delay],
        then capped at max_interval.

        Args:
            attempt: The attempt number (1-indexed). Attempt 1 means the first retry
                     (after the initial execution failed).

        Returns:
            Delay in seconds before the next retry.
        """
        initial = _parse_iso8601_duration(self.initial_interval)
        max_delay = _parse_iso8601_duration(self.max_interval)

        delay = initial * (self.backoff_coefficient ** (attempt - 1))
        delay = min(delay, max_delay)

        if self.jitter:
            delay = delay * random.uniform(0.5, 1.5)  # noqa: S311
            delay = min(delay, max_delay)

        return delay

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the OJS JSON wire format."""
        d: dict[str, Any] = {
            "max_attempts": self.max_attempts,
            "initial_interval": self.initial_interval,
            "backoff_coefficient": self.backoff_coefficient,
            "max_interval": self.max_interval,
            "jitter": self.jitter,
        }
        if self.non_retryable_errors:
            d["non_retryable_errors"] = self.non_retryable_errors
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        """Deserialize from the OJS JSON wire format."""
        return cls(
            max_attempts=data.get("max_attempts", 3),
            initial_interval=data.get("initial_interval", "PT1S"),
            backoff_coefficient=data.get("backoff_coefficient", 2.0),
            max_interval=data.get("max_interval", "PT5M"),
            jitter=data.get("jitter", True),
            non_retryable_errors=data.get("non_retryable_errors", []),
        )
