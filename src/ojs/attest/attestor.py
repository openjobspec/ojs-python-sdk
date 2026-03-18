"""Attestor protocol and concrete implementations."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from ojs.attest.types import (
    ALGORITHM_ED25519,
    QUOTE_TYPE_NONE,
    QUOTE_TYPE_PQC_ONLY,
    AttestInput,
    AttestResult,
    Quote,
    Signature,
    Receipt,
)


class AttestationNotAvailableError(Exception):
    """Hardware attestation is not available on this platform."""

    def __init__(self) -> None:
        super().__init__(
            "attest: hardware attestation not available on this platform"
        )


@runtime_checkable
class Attestor(Protocol):
    """Interface for all attestation implementations."""

    def name(self) -> str: ...

    def attest(self, envelope: AttestInput) -> AttestResult: ...

    def verify(self, receipt: Receipt) -> None: ...


# ---------------------------------------------------------------------------
# NoneAttestor
# ---------------------------------------------------------------------------


class NoneAttestor:
    """Default no-op attestor that always succeeds."""

    def name(self) -> str:
        return "none"

    def attest(self, envelope: AttestInput) -> AttestResult:
        return AttestResult(
            quote=Quote(
                type=QUOTE_TYPE_NONE,
                evidence=b"",
                nonce="",
                issued_at=envelope.timestamp,
            ),
            signature=Signature(algorithm=ALGORITHM_ED25519, value="", key_id=""),
        )

    def verify(self, receipt: Receipt) -> None:
        return


# ---------------------------------------------------------------------------
# PQCOnlyAttestor
# ---------------------------------------------------------------------------


class PQCOnlyAttestor:
    """Software-only PQC-ready attestor using HMAC-SHA256 (placeholder).

    A future version will use ML-DSA-65 once pure-Python implementations
    are available. For now HMAC-SHA256 provides integrity without requiring
    external dependencies.
    """

    def __init__(self, secret: bytes, key_id: str) -> None:
        self._secret = secret
        self._key_id = key_id

    def name(self) -> str:
        return "pqc-only"

    def attest(self, envelope: AttestInput) -> AttestResult:
        digest = _attest_digest(envelope)
        sig = hmac.new(self._secret, digest, hashlib.sha256).hexdigest()

        return AttestResult(
            quote=Quote(
                type=QUOTE_TYPE_PQC_ONLY,
                evidence=digest,
                nonce=digest[:16].hex(),
                issued_at=envelope.timestamp,
            ),
            signature=Signature(
                algorithm="hmac-sha256",
                value=sig,
                key_id=self._key_id,
            ),
        )

    def verify(self, receipt: Receipt) -> None:
        if receipt.quote is None:
            raise ValueError("attest: receipt has no quote")
        expected = hmac.new(
            self._secret, receipt.quote.evidence, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, receipt.signature.value):
            raise ValueError("attest: HMAC-SHA256 signature verification failed")


# ---------------------------------------------------------------------------
# Hardware stubs
# ---------------------------------------------------------------------------


class NitroAttestor:
    """Placeholder for AWS Nitro Enclave attestation."""

    def name(self) -> str:
        return "aws-nitro"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(self, receipt: Receipt) -> None:
        raise AttestationNotAvailableError()


class TDXAttestor:
    """Placeholder for Intel TDX attestation."""

    def name(self) -> str:
        return "intel-tdx"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(self, receipt: Receipt) -> None:
        raise AttestationNotAvailableError()


class SEVAttestor:
    """Placeholder for AMD SEV-SNP attestation."""

    def name(self) -> str:
        return "amd-sev-snp"

    def attest(self, envelope: AttestInput) -> AttestResult:
        raise AttestationNotAvailableError()

    def verify(self, receipt: Receipt) -> None:
        raise AttestationNotAvailableError()


def _attest_digest(e: AttestInput) -> bytes:
    """Compute SHA-256(args_hash || result_hash || timestamp)."""
    h = hashlib.sha256()
    h.update(e.args_hash.encode())
    h.update(e.result_hash.encode())
    h.update(e.timestamp.isoformat().encode())
    return h.digest()
