"""Canonical attestation payload construction and receipt verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ojs.attest.types import (
    AttestInput,
    Jurisdiction,
    ModelFingerprint,
    Quote,
    Receipt,
)

ATTESTATION_PAYLOAD_VERSION = "ojs-attest-v1"


class ReceiptVerificationError(ValueError):
    """An attestation receipt does not match its claimed envelope."""


def new_nonce() -> str:
    return secrets.token_hex(16)


def canonical_payload(
    envelope: AttestInput,
    *,
    quote_type: str,
    nonce: str,
    issued_at: datetime,
    algorithm: str,
    key_id: str,
    receipt_id: str = "",
    jurisdiction: Jurisdiction | None = None,
    model_fingerprint: ModelFingerprint | None = None,
) -> bytes:
    payload = {
        "algorithm": algorithm,
        "args_hash": envelope.args_hash,
        "issued_at": _timestamp(issued_at),
        "job_id": envelope.job_id,
        "job_type": envelope.job_type,
        "key_id": key_id,
        "jurisdiction": (
            {
                "datacenter": jurisdiction.datacenter,
                "prover": jurisdiction.prover,
                "region": jurisdiction.region,
            }
            if jurisdiction is not None
            else None
        ),
        "model_fingerprint": (
            {
                "registry_url": model_fingerprint.registry_url,
                "sha256": model_fingerprint.sha256,
            }
            if model_fingerprint is not None
            else None
        ),
        "nonce": nonce,
        "quote_type": quote_type,
        "receipt_id": receipt_id,
        "result_hash": envelope.result_hash,
        "timestamp": _timestamp(envelope.timestamp),
        "version": ATTESTATION_PAYLOAD_VERSION,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


class ReceiptVerifier:
    """Verify HMAC receipts against exact claims and freshness policy."""

    def __init__(
        self,
        secret: bytes,
        *,
        key_id: str,
        max_age: timedelta | None = timedelta(minutes=5),
        max_future_skew: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._secret = secret
        self._key_id = key_id
        self._max_age = max_age
        self._max_future_skew = max_future_skew
        self._clock = clock

    def verify(self, receipt: Receipt, envelope: AttestInput) -> None:
        quote = receipt.quote
        if quote is None:
            raise ReceiptVerificationError("attest: receipt has no quote")
        self._verify_claims(receipt, envelope, quote)
        expected_payload = canonical_payload(
            envelope,
            quote_type=quote.type,
            nonce=quote.nonce,
            issued_at=quote.issued_at,
            algorithm=receipt.signature.algorithm,
            key_id=receipt.signature.key_id,
            receipt_id=receipt.receipt_id,
            jurisdiction=receipt.jurisdiction,
            model_fingerprint=receipt.model_fingerprint,
        )
        if not hmac.compare_digest(expected_payload, quote.evidence):
            raise ReceiptVerificationError(
                "attest: quote evidence does not match the claimed envelope"
            )
        expected_signature = hmac.new(
            self._secret,
            expected_payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, receipt.signature.value):
            raise ReceiptVerificationError("attest: HMAC-SHA256 signature verification failed")
        self._verify_freshness(quote)

    def _verify_claims(
        self,
        receipt: Receipt,
        envelope: AttestInput,
        quote: Quote,
    ) -> None:
        if receipt.job_id != envelope.job_id:
            raise ReceiptVerificationError("attest: receipt job_id mismatch")
        if receipt.job_type != envelope.job_type:
            raise ReceiptVerificationError("attest: receipt job_type mismatch")
        if receipt.args_hash != envelope.args_hash:
            raise ReceiptVerificationError("attest: receipt args_hash mismatch")
        if receipt.result_hash != envelope.result_hash:
            raise ReceiptVerificationError("attest: receipt result_hash mismatch")
        if receipt.receipt_id != envelope.receipt_id:
            raise ReceiptVerificationError("attest: receipt_id mismatch")
        if receipt.signature.algorithm != "hmac-sha256":
            raise ReceiptVerificationError("attest: unexpected signature algorithm")
        if receipt.signature.key_id != self._key_id:
            raise ReceiptVerificationError("attest: unexpected signing key")
        if receipt.issued_at != quote.issued_at:
            raise ReceiptVerificationError("attest: receipt and quote timestamps differ")
        if quote.issued_at != envelope.timestamp:
            raise ReceiptVerificationError("attest: quote timestamp does not match envelope")
        if len(quote.nonce) < 32:
            raise ReceiptVerificationError("attest: quote nonce is too short")
        try:
            bytes.fromhex(quote.nonce)
        except ValueError as exc:
            raise ReceiptVerificationError("attest: quote nonce is not hexadecimal") from exc

    def _verify_freshness(self, quote: Quote) -> None:
        now = _aware(self._clock())
        issued_at = _aware(quote.issued_at)
        if issued_at - now > self._max_future_skew:
            raise ReceiptVerificationError("attest: quote timestamp is in the future")
        if self._max_age is not None and now - issued_at > self._max_age:
            raise ReceiptVerificationError("attest: quote is stale")


def _timestamp(value: datetime) -> str:
    return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReceiptVerificationError("attest: timestamps must be timezone-aware")
    return value


__all__ = [
    "ATTESTATION_PAYLOAD_VERSION",
    "ReceiptVerificationError",
    "ReceiptVerifier",
    "canonical_payload",
    "new_nonce",
]
