"""Attestor protocol and concrete implementations."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from ojs.attest.receipt_verifier import (
    ReceiptVerificationError,
    ReceiptVerifier,
    canonical_payload,
    new_nonce,
)
from ojs.attest.types import (
    ALGORITHM_NONE,
    QUOTE_TYPE_NONE,
    QUOTE_TYPE_PQC_ONLY,
    AttestInput,
    AttestResult,
    Quote,
    Receipt,
    Signature,
)


class AttestationNotAvailableError(Exception):
    """Hardware attestation is not available on this platform."""

    def __init__(self) -> None:
        super().__init__("attest: hardware attestation not available on this platform")


@runtime_checkable
class Attestor(Protocol):
    """Interface for all attestation implementations."""

    def name(self) -> str: ...

    def attest(self, envelope: AttestInput) -> AttestResult: ...

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# NoneAttestor
# ---------------------------------------------------------------------------


class NoneAttestor:
    """Default no-op attestor that always succeeds."""

    def name(self) -> str:
        return "none"

    def attest(self, envelope: AttestInput) -> AttestResult:
        nonce = new_nonce()
        evidence = canonical_payload(
            envelope,
            quote_type=QUOTE_TYPE_NONE,
            nonce=nonce,
            issued_at=envelope.timestamp,
            algorithm=ALGORITHM_NONE,
            key_id="",
            receipt_id=envelope.receipt_id,
        )
        return AttestResult(
            quote=Quote(
                type=QUOTE_TYPE_NONE,
                evidence=evidence,
                nonce=nonce,
                issued_at=envelope.timestamp,
            ),
            signature=Signature(algorithm=ALGORITHM_NONE, value="", key_id=""),
        )

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None:
        if receipt.quote is None:
            raise ReceiptVerificationError("attest: receipt has no quote")
        if receipt.quote.type != QUOTE_TYPE_NONE:
            raise ReceiptVerificationError("attest: unexpected quote type")
        if (
            receipt.signature.algorithm != ALGORITHM_NONE
            or receipt.signature.value
            or receipt.signature.key_id
        ):
            raise ReceiptVerificationError("attest: invalid no-op signature claims")
        if envelope is None:
            envelope = AttestInput(
                job_id=receipt.job_id,
                job_type=receipt.job_type,
                args_hash=receipt.args_hash,
                result_hash=receipt.result_hash,
                receipt_id=receipt.receipt_id,
                timestamp=receipt.quote.issued_at,
            )
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
        expected = canonical_payload(
            envelope,
            quote_type=receipt.quote.type,
            nonce=receipt.quote.nonce,
            issued_at=receipt.quote.issued_at,
            algorithm=ALGORITHM_NONE,
            key_id="",
            receipt_id=envelope.receipt_id,
            jurisdiction=receipt.jurisdiction,
            model_fingerprint=receipt.model_fingerprint,
        )
        if not hmac.compare_digest(expected, receipt.quote.evidence):
            raise ReceiptVerificationError(
                "attest: quote evidence does not match the claimed envelope"
            )


# ---------------------------------------------------------------------------
# PQCOnlyAttestor
# ---------------------------------------------------------------------------


class PQCOnlyAttestor:
    """Software-only PQC-ready attestor using HMAC-SHA256 (placeholder).

    A future version will use ML-DSA-65 once pure-Python implementations
    are available. For now HMAC-SHA256 provides integrity without requiring
    external dependencies.
    """

    def __init__(
        self,
        secret: bytes,
        key_id: str,
        *,
        max_age: timedelta | None = timedelta(minutes=5),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not secret:
            raise ValueError("attest: secret must not be empty")
        if not key_id:
            raise ValueError("attest: key_id must not be empty")
        self._secret = secret
        self._key_id = key_id
        self._verifier = ReceiptVerifier(
            secret,
            key_id=key_id,
            max_age=max_age,
            clock=clock,
        )

    def name(self) -> str:
        return "pqc-only"

    def attest(self, envelope: AttestInput) -> AttestResult:
        nonce = new_nonce()
        evidence = canonical_payload(
            envelope,
            quote_type=QUOTE_TYPE_PQC_ONLY,
            nonce=nonce,
            issued_at=envelope.timestamp,
            algorithm="hmac-sha256",
            key_id=self._key_id,
            receipt_id=envelope.receipt_id,
        )
        sig = hmac.new(self._secret, evidence, hashlib.sha256).hexdigest()

        return AttestResult(
            quote=Quote(
                type=QUOTE_TYPE_PQC_ONLY,
                evidence=evidence,
                nonce=nonce,
                issued_at=envelope.timestamp,
            ),
            signature=Signature(
                algorithm="hmac-sha256",
                value=sig,
                key_id=self._key_id,
            ),
        )

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None:
        if receipt.quote is None:
            raise ReceiptVerificationError("attest: receipt has no quote")
        if envelope is None:
            envelope = AttestInput(
                job_id=receipt.job_id,
                job_type=receipt.job_type,
                args_hash=receipt.args_hash,
                result_hash=receipt.result_hash,
                receipt_id=receipt.receipt_id,
                timestamp=receipt.quote.issued_at,
            )
        self._verifier.verify(receipt, envelope)


# ---------------------------------------------------------------------------
# Hardware stubs
# ---------------------------------------------------------------------------


class NitroAttestor:
    """Placeholder for AWS Nitro Enclave attestation."""

    def name(self) -> str:
        return "aws-nitro"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None:
        raise AttestationNotAvailableError()


class TDXAttestor:
    """Placeholder for Intel TDX attestation."""

    def name(self) -> str:
        return "intel-tdx"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None:
        raise AttestationNotAvailableError()


class SEVAttestor:
    """Placeholder for AMD SEV-SNP attestation."""

    def name(self) -> str:
        return "amd-sev-snp"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(
        self,
        receipt: Receipt,
        envelope: AttestInput | None = None,
    ) -> None:
        raise AttestationNotAvailableError()
