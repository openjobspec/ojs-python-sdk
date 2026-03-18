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


@dataclass(frozen=True)
class AttestInput:
    """Input envelope for attestation."""

    job_id: str
    job_type: str
    args_hash: str
    result_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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


@dataclass(frozen=True)
class Receipt:
    """Bundle a verifier needs to check an attestation."""

    job_id: str
    signature: Signature
    issued_at: datetime
    quote: Quote | None = None
    jurisdiction: Jurisdiction | None = None
    model_fingerprint: ModelFingerprint | None = None
