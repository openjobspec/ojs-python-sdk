"""Tests for envelope-bound OJS attestation receipts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ojs.attest import (
    AttestationNotAvailableError,
    AttestInput,
    NitroAttestor,
    NoneAttestor,
    PQCOnlyAttestor,
    Receipt,
    ReceiptVerificationError,
    SEVAttestor,
    Signature,
    TDXAttestor,
)
from ojs.attest.types import (
    ALGORITHM_NONE,
    QUOTE_TYPE_NONE,
    QUOTE_TYPE_PQC_ONLY,
    Jurisdiction,
    ModelFingerprint,
)

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _sample_input(*, timestamp: datetime = NOW) -> AttestInput:
    return AttestInput(
        job_id="job-1",
        job_type="ml.train",
        args_hash="sha256:aaa",
        result_hash="sha256:bbb",
        timestamp=timestamp,
    )


def _attestor() -> PQCOnlyAttestor:
    return PQCOnlyAttestor(
        secret=b"test-secret",
        key_id="key-1",
        clock=lambda: NOW,
    )


class TestNoneAttestor:
    def test_noop_algorithm_is_honest_and_envelope_bound(self) -> None:
        attestor = NoneAttestor()
        envelope = _sample_input()
        result = attestor.attest(envelope)
        receipt = result.to_receipt(envelope)

        assert attestor.name() == "none"
        assert result.quote is not None
        assert result.quote.type == QUOTE_TYPE_NONE
        assert result.signature.algorithm == ALGORITHM_NONE
        assert result.signature.value == ""
        attestor.verify(receipt, envelope)

        with pytest.raises(ReceiptVerificationError, match="result_hash mismatch"):
            attestor.verify(
                receipt,
                replace(envelope, result_hash="sha256:tampered"),
            )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("job_type", "other.type", "job_type mismatch"),
            ("args_hash", "sha256:changed", "args_hash mismatch"),
            ("result_hash", "sha256:changed", "result_hash mismatch"),
            ("receipt_id", "changed", "receipt_id mismatch"),
        ],
    )
    def test_noop_receipt_claims_must_match_envelope(
        self,
        field: str,
        value: str,
        message: str,
    ) -> None:
        envelope = replace(_sample_input(), receipt_id="receipt-1")
        attestor = NoneAttestor()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match=message):
            attestor.verify(replace(receipt, **{field: value}), envelope)


class TestPQCOnlyAttestor:
    def test_sign_and_verify_bound_receipt(self) -> None:
        attestor = _attestor()
        envelope = replace(_sample_input(), receipt_id="receipt-1")
        result = attestor.attest(envelope)
        receipt = result.to_receipt(envelope)

        assert attestor.name() == "pqc-only"
        assert result.quote is not None
        assert result.quote.type == QUOTE_TYPE_PQC_ONLY
        assert result.signature.value
        assert receipt.receipt_id == "receipt-1"
        attestor.verify(receipt, envelope)

    def test_receipt_id_must_be_bound_before_attestation(self) -> None:
        envelope = _sample_input()
        result = _attestor().attest(envelope)

        with pytest.raises(ValueError, match="AttestInput"):
            result.to_receipt(envelope, receipt_id="late-id")

    def test_one_argument_verification_authenticates_receipt_claims(self) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        attestor.verify(receipt)
        with pytest.raises(ReceiptVerificationError, match="claimed envelope"):
            attestor.verify(replace(receipt, job_id="job-tampered"))

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            (
                "jurisdiction",
                Jurisdiction(region="eu-west-1", datacenter="dc-1", prover="test"),
            ),
            (
                "model_fingerprint",
                ModelFingerprint(
                    sha256="sha256:model",
                    registry_url="https://models.example/model",
                ),
            ),
        ],
    )
    def test_unsigned_optional_claims_are_rejected(
        self,
        field: str,
        value: object,
    ) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match="claimed envelope"):
            attestor.verify(replace(receipt, **{field: value}))

    def test_cross_job_replay_is_rejected(self) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match="job_id mismatch"):
            attestor.verify(
                receipt,
                replace(envelope, job_id="job-2"),
            )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("job_type", "ml.predict", "job_type mismatch"),
            ("args_hash", "sha256:changed", "args_hash mismatch"),
            ("result_hash", "sha256:changed", "result_hash mismatch"),
            ("receipt_id", "receipt-tampered", "receipt_id mismatch"),
        ],
    )
    def test_modified_receipt_claim_is_rejected(
        self,
        field: str,
        value: str,
        message: str,
    ) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match=message):
            attestor.verify(replace(receipt, **{field: value}), envelope)

    @pytest.mark.parametrize("field", ["job_type", "args_hash", "result_hash"])
    def test_blank_required_receipt_claim_is_rejected(self, field: str) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match="mismatch"):
            attestor.verify(replace(receipt, **{field: ""}), envelope)

    @pytest.mark.parametrize(
        ("signature", "message"),
        [
            (
                Signature(
                    algorithm="ed25519",
                    value="invalid",
                    key_id="key-1",
                ),
                "algorithm",
            ),
            (
                Signature(
                    algorithm="hmac-sha256",
                    value="invalid",
                    key_id="other-key",
                ),
                "signing key",
            ),
            (
                Signature(
                    algorithm="hmac-sha256",
                    value="deadbeef" * 8,
                    key_id="key-1",
                ),
                "verification failed",
            ),
        ],
    )
    def test_wrong_algorithm_key_or_signature_is_rejected(
        self,
        signature: Signature,
        message: str,
    ) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match=message):
            attestor.verify(replace(receipt, signature=signature), envelope)

    def test_tampered_nonce_is_rejected(self) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)
        assert receipt.quote is not None
        tampered_quote = replace(receipt.quote, nonce="ab" * 16)

        with pytest.raises(ReceiptVerificationError, match="claimed envelope"):
            attestor.verify(replace(receipt, quote=tampered_quote), envelope)

    def test_stale_quote_is_rejected(self) -> None:
        old = NOW - timedelta(minutes=10)
        envelope = _sample_input(timestamp=old)
        attestor = _attestor()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match="stale"):
            attestor.verify(receipt, envelope)

    def test_receipt_timestamp_tampering_is_rejected(self) -> None:
        attestor = _attestor()
        envelope = _sample_input()
        receipt = attestor.attest(envelope).to_receipt(envelope)

        with pytest.raises(ReceiptVerificationError, match="timestamps differ"):
            attestor.verify(
                replace(receipt, issued_at=NOW + timedelta(seconds=1)),
                envelope,
            )

    def test_verify_no_quote(self) -> None:
        attestor = _attestor()
        receipt = Receipt(
            job_id="job-1",
            quote=None,
            signature=Signature(
                algorithm="hmac-sha256",
                value="x",
                key_id="key-1",
            ),
            issued_at=NOW,
        )

        with pytest.raises(ReceiptVerificationError, match="no quote"):
            attestor.verify(receipt, _sample_input())


class TestHardwareStubs:
    @pytest.mark.parametrize(
        ("attestor_type", "expected_name"),
        [
            (NitroAttestor, "aws-nitro"),
            (TDXAttestor, "intel-tdx"),
            (SEVAttestor, "amd-sev-snp"),
        ],
    )
    def test_not_available(
        self,
        attestor_type: type[NitroAttestor | TDXAttestor | SEVAttestor],
        expected_name: str,
    ) -> None:
        attestor = attestor_type()
        assert attestor.name() == expected_name

        with pytest.raises(AttestationNotAvailableError):
            attestor.attest(_sample_input())

        receipt = Receipt(
            job_id="job-1",
            quote=None,
            signature=Signature(algorithm="", value="", key_id=""),
            issued_at=NOW,
        )
        with pytest.raises(AttestationNotAvailableError):
            attestor.verify(receipt, _sample_input())
