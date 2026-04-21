"""Tests for transport-level rate limiting with Retry-After backoff."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from pytest_httpx import HTTPXMock

from ojs.errors import OJSAPIError, RateLimitedError
from ojs.transport.http import _OJS_BASE_PATH, HTTPTransport
from ojs.transport.http.retry_policy import (
    OperationSafety,
    RetryReason,
    classify_operation,
    retry_reason,
)
from ojs.transport.rate_limiter import (
    RetryConfig,
    calculate_backoff,
    sleep_before_retry,
)

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


class TestRetryPolicy:
    def test_classifies_methods_and_idempotency(self) -> None:
        assert classify_operation("GET") is OperationSafety.SAFE
        assert classify_operation("DELETE") is OperationSafety.IDEMPOTENT
        assert classify_operation("POST") is OperationSafety.UNSAFE
        assert (
            classify_operation("POST", idempotency_key="logical-operation")
            is OperationSafety.IDEMPOTENT
        )

    def test_unsafe_post_does_not_retry_ambiguous_server_error(self) -> None:
        assert (
            retry_reason(
                503,
                attempt=0,
                safety=OperationSafety.UNSAFE,
                config=RetryConfig(),
            )
            is None
        )


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


class TestRetryLogging:
    @pytest.mark.parametrize(
        "reason",
        [
            RetryReason.RATE_LIMITED,
            RetryReason.TRANSIENT_SERVER_ERROR,
        ],
    )
    async def test_logs_structured_retry_reason(
        self,
        reason: RetryReason,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with (
            patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.WARNING, logger="ojs.transport.rate_limiter"),
        ):
            await sleep_before_retry(
                0,
                None,
                RetryConfig(max_retries=3),
                reason=reason.value,
            )

        assert len(caplog.records) == 1
        assert f"reason={reason.value}" in caplog.records[0].message
        if reason is RetryReason.TRANSIENT_SERVER_ERROR:
            assert "429" not in caplog.records[0].message


class TestHTTPTransportRateLimitRetry:
    """Test automatic retry on 429 in HTTPTransport."""

    async def test_retries_on_429_then_succeeds(self, httpx_mock: HTTPXMock) -> None:
        """429 followed by 200 should retry and return success."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=429,
            json=RATE_LIMITED_BODY,
        )
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=200,
            json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch(
            "ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            job = await transport.push({"type": "email.send", "args": ["user@example.com"]})

        assert job.id == "019463ab-1234-7000-8000-000000000001"
        mock_sleep.assert_called_once()
        await transport.close()

    async def test_respects_retry_after_header(self, httpx_mock: HTTPXMock) -> None:
        """Retry-After header value should be used as the sleep delay."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=429,
            json=RATE_LIMITED_BODY,
            headers={"Retry-After": "2.5"},
        )
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=200,
            json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=30.0)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch(
            "ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
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
                url=url,
                method="POST",
                status_code=429,
                json=RATE_LIMITED_BODY,
            )

        cfg = RetryConfig(max_retries=2, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with (
            patch(
                "ojs.transport.rate_limiter.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            pytest.raises(RateLimitedError),
        ):
            await transport.push({"type": "email.send", "args": ["user@example.com"]})

        assert mock_sleep.await_count == 2
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

        with (
            patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(OJSAPIError),
        ):
            await transport.push({"type": "email.send", "args": ["user@example.com"]})

        mock_sleep.assert_not_called()
        await transport.close()

    async def test_disabled_retry_raises_immediately(self, httpx_mock: HTTPXMock) -> None:
        """When retry is disabled, 429 should raise immediately."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=429,
            json=RATE_LIMITED_BODY,
        )

        cfg = RetryConfig(enabled=False)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with (
            patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(RateLimitedError),
        ):
            await transport.push({"type": "email.send", "args": ["user@example.com"]})

        mock_sleep.assert_not_called()
        await transport.close()

    async def test_multiple_retries_before_success(self, httpx_mock: HTTPXMock) -> None:
        """Multiple 429s followed by success should work."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        for _ in range(3):
            httpx_mock.add_response(
                url=url,
                method="POST",
                status_code=429,
                json=RATE_LIMITED_BODY,
            )
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=200,
            json=JOB_RESPONSE,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with patch(
            "ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            job = await transport.push({"type": "email.send", "args": ["user@example.com"]})

        assert job.type == "email.send"
        assert mock_sleep.call_count == 3
        await transport.close()

    async def test_cancellation_during_retry_sleep(self, httpx_mock: HTTPXMock) -> None:
        """CancelledError during retry sleep should propagate immediately."""
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=429,
            json=RATE_LIMITED_BODY,
        )

        cfg = RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.02)
        transport = HTTPTransport(BASE_URL, retry_config=cfg)

        with (
            patch(
                "ojs.transport.rate_limiter.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=asyncio.CancelledError,
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await transport.push({"type": "email.send", "args": ["user@example.com"]})

        await transport.close()

    async def test_default_retry_config_on_transport(self) -> None:
        """Transport should have a default RetryConfig if none provided."""
        transport = HTTPTransport(BASE_URL)
        assert transport._retry_config.enabled is True
        assert transport._retry_config.max_retries == 3
        await transport.close()

    async def test_post_503_is_not_replayed_without_idempotency(
        self,
        httpx_mock: HTTPXMock,
    ) -> None:
        url = f"{BASE_URL}{_OJS_BASE_PATH}/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=503,
            json={"error": {"code": "BACKEND_UNAVAILABLE"}},
        )
        transport = HTTPTransport(
            BASE_URL,
            retry_config=RetryConfig(min_backoff=0.01, max_backoff=0.02),
        )

        with pytest.raises(OJSAPIError):
            await transport.push({"type": "email.send", "args": []})

        assert len(httpx_mock.get_requests()) == 1
        await transport.close()

    async def test_idempotency_key_is_stable_and_request_ids_are_distinct(
        self,
        httpx_mock: HTTPXMock,
    ) -> None:
        url = f"{BASE_URL}{_OJS_BASE_PATH}/bulk/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=503,
            json={"error": {"code": "BACKEND_UNAVAILABLE"}},
        )
        httpx_mock.add_response(url=url, method="POST", json={"ok": True})
        transport = HTTPTransport(
            BASE_URL,
            retry_config=RetryConfig(
                max_retries=1,
                min_backoff=0.01,
                max_backoff=0.02,
            ),
        )

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            result = await transport._do_request(
                "POST",
                f"{_OJS_BASE_PATH}/bulk/jobs",
                json={"jobs": []},
                idempotency_key="bulk-operation-42",
            )

        requests = httpx_mock.get_requests()
        assert result == {"ok": True}
        assert [request.headers["Idempotency-Key"] for request in requests] == [
            "bulk-operation-42",
            "bulk-operation-42",
        ]
        assert len({request.headers["X-Request-ID"] for request in requests}) == 2
        await transport.close()

    async def test_header_idempotency_enables_retry_and_precedes_body(
        self,
        httpx_mock: HTTPXMock,
    ) -> None:
        url = f"{BASE_URL}{_OJS_BASE_PATH}/bulk/jobs"
        httpx_mock.add_response(
            url=url,
            method="POST",
            status_code=503,
            json={"error": {"code": "BACKEND_UNAVAILABLE"}},
        )
        httpx_mock.add_response(url=url, method="POST", json={"ok": True})
        transport = HTTPTransport(
            BASE_URL,
            headers={"Idempotency-Key": "header-operation"},
            retry_config=RetryConfig(
                max_retries=1,
                min_backoff=0.01,
                max_backoff=0.02,
            ),
        )

        with patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock):
            result = await transport._request(
                "POST",
                "/bulk/jobs",
                json={
                    "jobs": [],
                    "idempotency_key": "body-operation",
                },
            )

        requests = httpx_mock.get_requests()
        assert result == {"ok": True}
        assert [request.headers["Idempotency-Key"] for request in requests] == [
            "header-operation",
            "header-operation",
        ]
        await transport.close()

    async def test_get_server_error_retries_within_budget(
        self,
        httpx_mock: HTTPXMock,
    ) -> None:
        url = f"{BASE_URL}{_OJS_BASE_PATH}/health"
        for _ in range(2):
            httpx_mock.add_response(
                url=url,
                method="GET",
                status_code=503,
                json={"error": {"code": "BACKEND_UNAVAILABLE"}},
            )
        transport = HTTPTransport(
            BASE_URL,
            retry_config=RetryConfig(
                max_retries=1,
                min_backoff=0.01,
                max_backoff=0.02,
            ),
        )

        with (
            patch("ojs.transport.rate_limiter.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(OJSAPIError),
        ):
            await transport.health()

        assert len(httpx_mock.get_requests()) == 2
        await transport.close()
