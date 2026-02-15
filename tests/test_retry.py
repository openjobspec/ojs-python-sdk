"""Tests for the OJS retry policy."""

from __future__ import annotations

import pytest

from ojs.retry import RetryPolicy, _parse_iso8601_duration, _seconds_to_iso8601


class TestIso8601Duration:
    def test_parse_seconds(self) -> None:
        assert _parse_iso8601_duration("PT1S") == 1.0
        assert _parse_iso8601_duration("PT30S") == 30.0

    def test_parse_minutes(self) -> None:
        assert _parse_iso8601_duration("PT5M") == 300.0
        assert _parse_iso8601_duration("PT1M30S") == 90.0

    def test_parse_hours(self) -> None:
        assert _parse_iso8601_duration("PT1H") == 3600.0
        assert _parse_iso8601_duration("PT1H30M") == 5400.0

    def test_parse_days(self) -> None:
        assert _parse_iso8601_duration("P1D") == 86400.0
        assert _parse_iso8601_duration("P1DT12H") == 129600.0

    def test_parse_combined(self) -> None:
        assert _parse_iso8601_duration("P2DT3H15M45S") == 2 * 86400 + 3 * 3600 + 15 * 60 + 45

    def test_parse_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid ISO 8601 duration"):
            _parse_iso8601_duration("invalid")

        with pytest.raises(ValueError, match="Invalid ISO 8601 duration"):
            _parse_iso8601_duration("5s")

    def test_seconds_to_iso8601(self) -> None:
        assert _seconds_to_iso8601(0) == "PT0S"
        assert _seconds_to_iso8601(1) == "PT1S"
        assert _seconds_to_iso8601(60) == "PT1M"
        assert _seconds_to_iso8601(3600) == "PT1H"
        assert _seconds_to_iso8601(3661) == "PT1H1M1S"


class TestRetryPolicy:
    def test_defaults(self) -> None:
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.initial_interval == "PT1S"
        assert policy.backoff_coefficient == 2.0
        assert policy.max_interval == "PT5M"
        assert policy.jitter is True
        assert policy.non_retryable_errors == []

    def test_delay_for_attempt_no_jitter(self) -> None:
        policy = RetryPolicy(
            initial_interval="PT1S",
            backoff_coefficient=2.0,
            max_interval="PT5M",
            jitter=False,
        )
        assert policy.delay_for_attempt(1) == 1.0  # 1 * 2^0
        assert policy.delay_for_attempt(2) == 2.0  # 1 * 2^1
        assert policy.delay_for_attempt(3) == 4.0  # 1 * 2^2
        assert policy.delay_for_attempt(4) == 8.0  # 1 * 2^3
        assert policy.delay_for_attempt(5) == 16.0  # 1 * 2^4

    def test_delay_capped_at_max_interval(self) -> None:
        policy = RetryPolicy(
            initial_interval="PT1S",
            backoff_coefficient=10.0,
            max_interval="PT10S",
            jitter=False,
        )
        assert policy.delay_for_attempt(1) == 1.0
        assert policy.delay_for_attempt(2) == 10.0  # capped at max_interval
        assert policy.delay_for_attempt(3) == 10.0  # still capped

    def test_delay_with_jitter_in_range(self) -> None:
        policy = RetryPolicy(
            initial_interval="PT10S",
            backoff_coefficient=1.0,
            max_interval="PT1H",
            jitter=True,
        )
        # With jitter, delay should be in [5, 15] (10 * [0.5, 1.5])
        for _ in range(100):
            delay = policy.delay_for_attempt(1)
            assert 5.0 <= delay <= 15.0

    def test_to_dict(self) -> None:
        policy = RetryPolicy(
            max_attempts=5,
            initial_interval="PT2S",
            non_retryable_errors=["validation_error"],
        )
        d = policy.to_dict()
        assert d["max_attempts"] == 5
        assert d["initial_interval"] == "PT2S"
        assert d["non_retryable_errors"] == ["validation_error"]

    def test_from_dict(self) -> None:
        d = {
            "max_attempts": 10,
            "initial_interval": "PT5S",
            "backoff_coefficient": 3.0,
            "max_interval": "PT10M",
            "jitter": False,
            "non_retryable_errors": ["not_found"],
        }
        policy = RetryPolicy.from_dict(d)
        assert policy.max_attempts == 10
        assert policy.initial_interval == "PT5S"
        assert policy.backoff_coefficient == 3.0
        assert policy.jitter is False
        assert policy.non_retryable_errors == ["not_found"]

    def test_from_dict_defaults(self) -> None:
        policy = RetryPolicy.from_dict({})
        assert policy.max_attempts == 3
        assert policy.initial_interval == "PT1S"

    def test_roundtrip(self) -> None:
        original = RetryPolicy(
            max_attempts=7,
            initial_interval="PT3S",
            backoff_coefficient=1.5,
            max_interval="PT1H",
            jitter=False,
            non_retryable_errors=["auth_error"],
        )
        restored = RetryPolicy.from_dict(original.to_dict())
        assert original == restored
