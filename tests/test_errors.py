"""Tests for OJS error types and raise_for_error mapping."""

import pytest

import ojs
from ojs.errors import OJSErrorDetail, RateLimitInfo, raise_for_error


class TestOJSErrorDetail:
    def test_defaults(self) -> None:
        detail = OJSErrorDetail(code="test", message="msg", retryable=False)
        assert detail.details == {}
        assert detail.request_id is None

    def test_with_all_fields(self) -> None:
        detail = OJSErrorDetail(
            code="handler_error",
            message="boom",
            retryable=True,
            details={"traceback": "..."},
            request_id="req-123",
        )
        assert detail.code == "handler_error"
        assert detail.retryable is True
        assert detail.details["traceback"] == "..."
        assert detail.request_id == "req-123"


class TestOJSAPIError:
    def test_properties(self) -> None:
        detail = OJSErrorDetail(code="bad_request", message="invalid", retryable=False)
        err = ojs.OJSAPIError(400, detail)
        assert err.status_code == 400
        assert err.code == "bad_request"
        assert err.retryable is False
        assert "400" in str(err)
        assert "bad_request" in str(err)

    def test_retryable_flag(self) -> None:
        detail = OJSErrorDetail(code="server_error", message="oops", retryable=True)
        err = ojs.OJSAPIError(500, detail)
        assert err.retryable is True


class TestErrorHierarchy:
    def test_all_api_errors_are_ojs_errors(self) -> None:
        detail = OJSErrorDetail(code="test", message="msg", retryable=False)
        assert isinstance(ojs.OJSAPIError(400, detail), ojs.OJSError)
        assert isinstance(ojs.DuplicateJobError(409, detail), ojs.OJSError)
        assert isinstance(ojs.JobNotFoundError(404, detail), ojs.OJSError)
        assert isinstance(ojs.QueuePausedError(422, detail), ojs.OJSError)
        assert isinstance(ojs.RateLimitedError(429, detail), ojs.OJSError)

    def test_connection_error_is_ojs_error(self) -> None:
        assert isinstance(ojs.OJSConnectionError("fail"), ojs.OJSError)

    def test_timeout_error_is_ojs_error(self) -> None:
        assert isinstance(ojs.OJSTimeoutError("timeout"), ojs.OJSError)

    def test_validation_error_is_ojs_error(self) -> None:
        assert isinstance(ojs.OJSValidationError("bad input"), ojs.OJSError)

    def test_specific_errors_are_api_errors(self) -> None:
        detail = OJSErrorDetail(code="test", message="msg", retryable=False)
        assert isinstance(ojs.DuplicateJobError(409, detail), ojs.OJSAPIError)
        assert isinstance(ojs.JobNotFoundError(404, detail), ojs.OJSAPIError)
        assert isinstance(ojs.QueuePausedError(422, detail), ojs.OJSAPIError)
        assert isinstance(ojs.RateLimitedError(429, detail), ojs.OJSAPIError)


class TestRateLimitedError:
    def test_retry_after(self) -> None:
        detail = OJSErrorDetail(code="rate_limited", message="slow down", retryable=True)
        err = ojs.RateLimitedError(429, detail, retry_after=30.0)
        assert err.retry_after == 30.0

    def test_retry_after_none(self) -> None:
        detail = OJSErrorDetail(code="rate_limited", message="slow down", retryable=True)
        err = ojs.RateLimitedError(429, detail)
        assert err.retry_after is None

    def test_rate_limit_info(self) -> None:
        detail = OJSErrorDetail(code="rate_limited", message="slow down", retryable=True)
        rl = RateLimitInfo(limit=100, remaining=0, reset=1700000000, retry_after=30.0)
        err = ojs.RateLimitedError(429, detail, retry_after=30.0, rate_limit=rl)
        assert err.rate_limit is not None
        assert err.rate_limit.limit == 100
        assert err.rate_limit.remaining == 0
        assert err.rate_limit.reset == 1700000000
        assert err.rate_limit.retry_after == 30.0

    def test_rate_limit_defaults_to_none(self) -> None:
        detail = OJSErrorDetail(code="rate_limited", message="slow down", retryable=True)
        err = ojs.RateLimitedError(429, detail)
        assert err.rate_limit is None


class TestRaiseForError:
    def test_duplicate_error(self) -> None:
        body = {"error": {"code": "duplicate", "message": "exists", "retryable": False}}
        with pytest.raises(ojs.DuplicateJobError) as exc_info:
            raise_for_error(409, body, None)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "duplicate"

    def test_not_found_error(self) -> None:
        body = {"error": {"code": "not_found", "message": "missing", "retryable": False}}
        with pytest.raises(ojs.JobNotFoundError) as exc_info:
            raise_for_error(404, body, None)
        assert exc_info.value.status_code == 404

    def test_queue_paused_error(self) -> None:
        body = {"error": {"code": "queue_paused", "message": "paused", "retryable": False}}
        with pytest.raises(ojs.QueuePausedError):
            raise_for_error(422, body, None)

    def test_rate_limited_error_with_retry_after_header(self) -> None:
        body = {"error": {"code": "rate_limited", "message": "slow", "retryable": True}}
        headers = {"retry-after": "60"}
        with pytest.raises(ojs.RateLimitedError) as exc_info:
            raise_for_error(429, body, headers)
        assert exc_info.value.retry_after == 60.0
        assert exc_info.value.retryable is True

    def test_rate_limited_error_with_full_headers(self) -> None:
        body = {"error": {"code": "rate_limited", "message": "slow", "retryable": True}}
        headers = {
            "retry-after": "30",
            "x-ratelimit-limit": "1000",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1700000000",
        }
        with pytest.raises(ojs.RateLimitedError) as exc_info:
            raise_for_error(429, body, headers)
        assert exc_info.value.retry_after == 30.0
        assert exc_info.value.rate_limit is not None
        assert exc_info.value.rate_limit.limit == 1000
        assert exc_info.value.rate_limit.remaining == 0
        assert exc_info.value.rate_limit.reset == 1700000000
        assert exc_info.value.rate_limit.retry_after == 30.0

    def test_rate_limited_error_without_retry_after(self) -> None:
        body = {"error": {"code": "rate_limited", "message": "slow", "retryable": True}}
        with pytest.raises(ojs.RateLimitedError) as exc_info:
            raise_for_error(429, body, None)
        assert exc_info.value.retry_after is None

    def test_rate_limited_error_invalid_retry_after(self) -> None:
        body = {"error": {"code": "rate_limited", "message": "slow", "retryable": True}}
        headers = {"retry-after": "not-a-number"}
        with pytest.raises(ojs.RateLimitedError) as exc_info:
            raise_for_error(429, body, headers)
        assert exc_info.value.retry_after is None

    def test_generic_api_error(self) -> None:
        body = {"error": {"code": "internal", "message": "oops", "retryable": True}}
        with pytest.raises(ojs.OJSAPIError) as exc_info:
            raise_for_error(500, body, None)
        assert exc_info.value.status_code == 500
        assert exc_info.value.code == "internal"

    def test_missing_error_fields_use_defaults(self) -> None:
        body = {"error": {}}
        with pytest.raises(ojs.OJSAPIError) as exc_info:
            raise_for_error(500, body, None)
        assert exc_info.value.code == "unknown"
        assert exc_info.value.retryable is False

    def test_empty_body(self) -> None:
        with pytest.raises(ojs.OJSAPIError) as exc_info:
            raise_for_error(500, {}, None)
        assert exc_info.value.code == "unknown"

    def test_error_detail_with_request_id(self) -> None:
        body = {
            "error": {
                "code": "internal",
                "message": "fail",
                "retryable": False,
                "request_id": "req-abc-123",
                "details": {"stack": "traceback here"},
            }
        }
        with pytest.raises(ojs.OJSAPIError) as exc_info:
            raise_for_error(500, body, None)
        assert exc_info.value.error.request_id == "req-abc-123"
        assert exc_info.value.error.details["stack"] == "traceback here"
