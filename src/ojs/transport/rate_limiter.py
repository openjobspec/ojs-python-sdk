"""Rate limiting with automatic retry and Retry-After backoff.

Provides transport-level retry logic for HTTP 429 (Too Many Requests)
responses, with exponential backoff and jitter.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

logger = logging.getLogger("ojs.transport.rate_limiter")


@dataclass
class RetryConfig:
    """Configuration for automatic 429 rate-limit retries.

    Attributes:
        max_retries: Maximum number of retry attempts on 429. Default: 3.
        min_backoff: Minimum backoff delay in seconds. Default: 0.5.
        max_backoff: Maximum backoff delay in seconds. Default: 30.0.
        enabled: Whether automatic retry is enabled. Default: True.
    """

    max_retries: int = 3
    min_backoff: float = 0.5
    max_backoff: float = 30.0
    enabled: bool = True


def calculate_backoff(
    attempt: int,
    retry_after: float | None,
    config: RetryConfig,
) -> float:
    """Calculate the backoff delay for a retry attempt.

    If a Retry-After value is present, it is used as the base delay
    (clamped to max_backoff). Otherwise, exponential backoff with
    jitter is applied.

    Args:
        attempt: The current retry attempt number (0-indexed).
        retry_after: The Retry-After header value in seconds, if any.
        config: The retry configuration.

    Returns:
        Delay in seconds before the next retry.
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after, config.max_backoff)

    # Exponential backoff with decorrelated jitter: base * random(0.5, 1.0)
    base = config.min_backoff * (2 ** attempt)
    backoff = min(base, config.max_backoff)
    jitter = 0.5 + random.random() * 0.5  # noqa: S311
    return backoff * jitter


async def sleep_before_retry(
    attempt: int,
    retry_after: float | None,
    config: RetryConfig,
) -> None:
    """Sleep for the calculated backoff duration before retrying.

    Args:
        attempt: The current retry attempt number (0-indexed).
        retry_after: The Retry-After header value in seconds, if any.
        config: The retry configuration.
    """
    delay = calculate_backoff(attempt, retry_after, config)
    logger.warning(
        "Rate limited (429). Retry %d/%d after %.2fs",
        attempt + 1,
        config.max_retries,
        delay,
    )
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        # Propagate cancellation immediately — do not swallow it.
        raise
