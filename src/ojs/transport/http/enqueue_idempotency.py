"""Idempotency identity handling for retryable HTTP mutations."""

from __future__ import annotations

from collections.abc import Mapping

_MAX_IDEMPOTENCY_KEY_LENGTH = 256


def _validate_idempotency_key(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("idempotency key must be a non-empty string")
    if len(value) > _MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(
            f"idempotency key must not exceed {_MAX_IDEMPOTENCY_KEY_LENGTH} characters"
        )
    return value


def idempotency_key_from_body(body: object) -> str | None:
    """Extract a protocol idempotency key from a request body when present."""
    if not isinstance(body, Mapping):
        return None
    return _validate_idempotency_key(body.get("idempotency_key"))


def effective_idempotency_key(
    headers: Mapping[str, str],
    body: object,
) -> str | None:
    """Resolve one logical identity, preferring an explicit HTTP header."""
    header_key = _validate_idempotency_key(headers.get("Idempotency-Key"))
    return header_key if header_key is not None else idempotency_key_from_body(body)


def request_headers(idempotency_key: str | None) -> dict[str, str]:
    """Build per-attempt headers while retaining one logical identity."""
    import uuid

    headers = {"X-Request-ID": str(uuid.uuid4())}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


__all__ = [
    "effective_idempotency_key",
    "idempotency_key_from_body",
    "request_headers",
]
