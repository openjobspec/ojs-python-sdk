"""Attestation data types for OJS verifiable compute."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Quote type constants.
QUOTE_TYPE_AWS_NITRO: str = "aws-nitro-v1"
QUOTE_TYPE_INTEL_TDX: str = "intel-tdx-v4"
QUOTE_TYPE_AMD_SEV_SNP: str = "amd-sev-snp-v2"
QUOTE_TYPE_PQC_ONLY: str = "pqc-only"
QUOTE_TYPE_NONE: str = "none"

# Signature algorithm constants.
ALGORITHM_ED25519: str = "ed25519"
ALGORITHM_ML_DSA_65: str = "ml-dsa-65"
ALGORITHM_HYBRID_ED_ML_DSA: str = "hybrid:Ed25519+ML-DSA-65"
ALGORITHM_NONE: str = "none"


@dataclass(frozen=True)
class AttestInput:
    """Input envelope for attestation."""

    job_id: str
    job_type: str
    args_hash: str
    result_hash: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc  # noqa: UP017 - public default compatibility
        )
    )
    receipt_id: str = ""


@dataclass(frozen=True)
class Quote:
    """Attestation evidence produced by the TEE or software layer."""

    type: str
    evidence: bytes
    nonce: str
    issued_at: datetime


@dataclass(frozen=True)
class Jurisdiction:
    """Where the attestation was produced."""

    region: str
    datacenter: str
    prover: str


@dataclass(frozen=True)
class ModelFingerprint:
    """ML model identity for auditability."""

    sha256: str
    registry_url: str


@dataclass(frozen=True)
class Signature:
    """Cryptographic signature over the attestation."""

    algorithm: str
    value: str
    key_id: str


@dataclass(frozen=True)
class AttestResult:
    """Result of a successful attestation."""

    quote: Quote | None = None
    jurisdiction: Jurisdiction | None = None
    model_fingerprint: ModelFingerprint | None = None
    signature: Signature = field(
        default_factory=lambda: Signature(algorithm="", value="", key_id="")
    )

    def to_receipt(
        self,
        envelope: AttestInput,
        *,
        receipt_id: str = "",
    ) -> Receipt:
        """Bind this result to the envelope claims used to produce it."""
        resolved_receipt_id = receipt_id or envelope.receipt_id
        if resolved_receipt_id != envelope.receipt_id:
            raise ValueError("receipt_id must be supplied on AttestInput before attestation")
        issued_at = self.quote.issued_at if self.quote is not None else envelope.timestamp
        return Receipt(
            job_id=envelope.job_id,
            signature=self.signature,
            issued_at=issued_at,
            quote=self.quote,
            jurisdiction=self.jurisdiction,
            model_fingerprint=self.model_fingerprint,
            job_type=envelope.job_type,
            args_hash=envelope.args_hash,
            result_hash=envelope.result_hash,
            receipt_id=resolved_receipt_id,
        )


@dataclass(frozen=True)
class Receipt:
    """Bundle a verifier needs to check an attestation."""

    job_id: str
    signature: Signature
    issued_at: datetime
    quote: Quote | None = None
    jurisdiction: Jurisdiction | None = None
    model_fingerprint: ModelFingerprint | None = None
    job_type: str = ""
    args_hash: str = ""
    result_hash: str = ""
    receipt_id: str = ""
