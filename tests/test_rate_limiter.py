"""Tests for transport-level rate limiting with Retry-After backoff."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from ojs.errors import RateLimitedError
from ojs.transport.http import HTTPTransport, _OJS_BASE_PATH
from ojs.transport.rate_limiter import RetryConfig, calculate_backoff

BASE_URL = "http://localhost:8080"

RATE_LIMITED_BODY = {
    "error": {
        "code": "rate_limited",
        "message": "Too many requests",
        "retryable": True,
    }
}

JOB_RESPONSE = {
    "job": {
        "id": "019463ab-1234-7000-8000-000000000001",
        "type": "email.send",
        "state": "available",
        "args": ["user@example.com"],
        "queue": "default",
        "priority": 0,
        "attempt": 0,
        "max_attempts": 3,
    }
}


class TestRetryConfig:
    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.min_backoff == 0.5
        assert cfg.max_backoff == 30.0
        assert cfg.enabled is True

    def test_custom_values(self) -> None:
        cfg = RetryConfig(max_retries=5, min_backoff=1.0, max_backoff=60.0, enabled=False)
        assert cfg.max_retries == 5
        assert cfg.min_backoff == 1.0
        assert cfg.max_backoff == 60.0
        assert cfg.enabled is False


class TestCalculateBackoff:
    def test_uses_retry_after_when_present(self) -> None:
        cfg = RetryConfig()
        delay = calculate_backoff(0, retry_after=2.0, config=cfg)
        assert delay == 2.0

    def test_retry_after_clamped_to_max(self) -> None:
        cfg = RetryConfig(max_backoff=5.0)
        delay = calculate_backoff(0, retry_after=10.0, config=cfg)
        assert delay == 5.0

    def test_exponential_backoff_without_retry_after(self) -> None:
        cfg = RetryConfig(min_backoff=1.0, max_backoff=100.0)
        delay_0 = calculate_backoff(0, retry_after=None, config=cfg)
        # attempt 0: min(1.0 * 2^0, 100) * rand(0.5, 1.0) = [0.5, 1.0)
        assert 0.5 <= delay_0 <= 1.0

        delay_2 = calculate_backoff(2, retry_after=None, config=cfg)
        # attempt 2: min(1.0 * 2^2, 100) * rand(0.5, 1.0) = [2.0, 4.0)
        assert 2.0 <= delay_2 <= 4.0

    def test_backoff_clamped_to_max(self) -> None:
        cfg = RetryConfig(min_backoff=1.0, max_backoff=3.0)
        delay = calculate_backoff(10, retry_after=None, config=cfg)
        assert delay <= 3.0


class TestHTTPTransportRateLimitRetry:
    """Test automatic retry on 429 in HTTPTransport."""

    async def test_retries_on_429_then_succeeds(self, httpx_mock: HTTPXMock) -> None:
        """429 followed by 200 should retry and return success."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
        )
        httpx_mock.add_response(
            url=url, method="POST", status_code=200, json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            job = await transport.push({"type": "email.send", "args": ["user@example.com"]})

        assert job.id == "019463ab-1234-7000-8000-000000000001"
        mock_sleep.assert_called_once()
        await transport.close()

    async def test_respects_retry_after_header(self, httpx_mock: HTTPXMock) -> None:
        """Retry-After header value should be used as the sleep delay."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
            headers={"Retry-After": "2.5"},
        )
        httpx_mock.add_response(
            url=url, method="POST", status_code=200, json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=30.0)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await transport.push({"type": "email.send", "args": ["user@example.com"]})

        # The sleep delay should match the Retry-After header
        mock_sleep.assert_called_once()
        actual_delay = mock_sleep.call_args[0][0]
        assert actual_delay == 2.5
        await transport.close()

    async def test_raises_after_max_retries(self, httpx_mock: HTTPXMock) -> None:
        """Should raise RateLimitedError after exhausting all retries."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        # 1 initial + 2 retries = 3 responses, all 429
        for _ in range(3):
            httpx_mock.add_response(
                url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
            )

        cfg = RetryConfig(max_retries=2, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RateLimitedError):
                await transport.push({"type": "email.send", "args": ["user@example.com"]})

        await transport.close()

    async def test_non_429_errors_not_retried(self, httpx_mock: HTTPXMock) -> None:
        """Non-429 errors should be raised immediately without retry."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=500,
            json={
                "error": {
                    "code": "internal",
                    "message": "Internal server error",
                    "retryable": False,
                }
            },
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(Exception):  # noqa: B017, PT011
                await transport.push({"type": "email.send", "args": ["user@example.com"]})

        mock_sleep.assert_not_called()
        await transport.close()

    async def test_disabled_retry_raises_immediately(self, httpx_mock: HTTPXMock) -> None:
        """When retry is disabled, 429 should raise immediately."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
        )

        cfg = RetryConfig(enabled=False)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RateLimitedError):
                await transport.push({"type": "email.send", "args": ["user@example.com"]})

        mock_sleep.assert_not_called()
        await transport.close()

    async def test_multiple_retries_before_success(self, httpx_mock: HTTPXMock) -> None:
        """Multiple 429s followed by success should work."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        for _ in range(3):
            httpx_mock.add_response(
                url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
            )
        httpx_mock.add_response(
            url=url, method="POST", status_code=200, json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            job = await transport.push({"type": "email.send", "args": ["user@example.com"]})

        assert job.type == "email.send"
        assert mock_sleep.call_count == 3
        await transport.close()

    async def test_cancellation_during_retry_sleep(self, httpx_mock: HTTPXMock) -> None:
        """CancelledError during retry sleep should propagate immediately."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url, method="POST", status_code=429, json=RATE_LIMITED_BODY,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch(
            "ojs.transport.rate_limiter.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError,
        ):
            with pytest.raises(asyncio.CancelledError):
                await transport.push({"type": "email.send", "args": ["user@example.com"]})

        await transport.close()

    async def test_default_retry_config_on_transport(self) -> None:
        """Transport should have a default RetryConfig if none provided."""
        transport = HTTPTransport(BASE_URL)
        assert transport._retry_config.enabled is True
        assert transport._retry_config.max_retries == 3
        await transport.close()
