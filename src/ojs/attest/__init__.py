"""OJS Verifiable Compute Attestation.

.. note::

   This module is part of **OJS Labs** — forward-looking R&D that is not
   part of the core release train. APIs may change between minor versions.

Provides attestation interfaces and implementations for hardware-backed
(AWS Nitro, Intel TDX, AMD SEV-SNP) and software-only (PQC / HMAC-SHA256)
verifiable compute.

Usage::

    from ojs.attest import NoneAttestor, PQCOnlyAttestor, AttestInput

    attestor = NoneAttestor()
    result = attestor.attest(AttestInput(
        job_id="job-1",
        job_type="ml.train",
        args_hash="sha256:abc",
        result_hash="sha256:def",
    ))
"""

from ojs.attest.attestor import (
    AttestationNotAvailableError,
    Attestor,
    NitroAttestor,
    NoneAttestor,
    PQCOnlyAttestor,
    SEVAttestor,
    TDXAttestor,
)
from ojs.attest.receipt_verifier import ReceiptVerificationError, ReceiptVerifier
from ojs.attest.types import (
    AttestInput,
    AttestResult,
    Jurisdiction,
    ModelFingerprint,
    Quote,
    Receipt,
    Signature,
)

__all__ = [
    "AttestInput",
    "AttestResult",
    "AttestationNotAvailableError",
    "Attestor",
    "Jurisdiction",
    "ModelFingerprint",
    "NitroAttestor",
    "NoneAttestor",
    "PQCOnlyAttestor",
    "Quote",
    "Receipt",
    "ReceiptVerificationError",
    "ReceiptVerifier",
    "SEVAttestor",
    "Signature",
    "TDXAttestor",
]
