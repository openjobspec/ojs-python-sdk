"""Tests for the OJS attestation module."""

from datetime import datetime, timezone

import pytest

from ojs.attest import (
    AttestInput,
    NoneAttestor,
    PQCOnlyAttestor,
    NitroAttestor,
    TDXAttestor,
    SEVAttestor,
    AttestationNotAvailableError,
    Receipt,
    Signature,
)
from ojs.attest.types import QUOTE_TYPE_NONE, QUOTE_TYPE_PQC_ONLY


def _sample_input() -> AttestInput:
    return AttestInput(
        job_id="job-1",
        job_type="ml.train",
        args_hash="sha256:aaa",
        result_hash="sha256:bbb",
        timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestNoneAttestor:
    def test_name(self) -> None:
        a = NoneAttestor()
        assert a.name() == "none"

    def test_attest_returns_result(self) -> None:
        a = NoneAttestor()
        result = a.attest(_sample_input())
        assert result is not None
        assert result.quote is not None
        assert result.quote.type == QUOTE_TYPE_NONE

    def test_verify_succeeds(self) -> None:
        a = NoneAttestor()
        result = a.attest(_sample_input())
        receipt = Receipt(
            job_id="job-1",
            quote=result.quote,
            signature=result.signature,
            issued_at=datetime.now(timezone.utc),
        )
        a.verify(receipt)  # should not raise


class TestPQCOnlyAttestor:
    def test_sign_and_verify(self) -> None:
        a = PQCOnlyAttestor(secret=b"test-secret", key_id="key-1")
        assert a.name() == "pqc-only"

        inp = _sample_input()
        result = a.attest(inp)

        assert result.quote is not None
        assert result.quote.type == QUOTE_TYPE_PQC_ONLY
        assert result.signature.value != ""
        assert result.signature.key_id == "key-1"

        receipt = Receipt(
            job_id=inp.job_id,
            quote=result.quote,
            signature=result.signature,
            issued_at=datetime.now(timezone.utc),
        )
        a.verify(receipt)  # should not raise

    def test_verify_bad_signature(self) -> None:
        a = PQCOnlyAttestor(secret=b"test-secret", key_id="key-1")
        inp = _sample_input()
        result = a.attest(inp)

        bad_receipt = Receipt(
            job_id=inp.job_id,
            quote=result.quote,
            signature=Signature(
                algorithm=result.signature.algorithm,
                value="deadbeef" * 8,
                key_id=result.signature.key_id,
            ),
            issued_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValueError, match="verification failed"):
            a.verify(bad_receipt)

    def test_verify_no_quote(self) -> None:
        a = PQCOnlyAttestor(secret=b"test-secret", key_id="key-1")
        receipt = Receipt(
            job_id="job-1",
            quote=None,
            signature=Signature(algorithm="hmac-sha256", value="x", key_id="k"),
            issued_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValueError, match="no quote"):
            a.verify(receipt)


class TestHardwareStubs:
    @pytest.mark.parametrize(
        "cls,expected_name",
        [
            (NitroAttestor, "aws-nitro"),
            (TDXAttestor, "intel-tdx"),
            (SEVAttestor, "amd-sev-snp"),
        ],
    )
    def test_not_available(self, cls: type, expected_name: str) -> None:
        a = cls()
        assert a.name() == expected_name

        with pytest.raises(AttestationNotAvailableError):
            a.attest(_sample_input())

        receipt = Receipt(
            job_id="job-1",
            quote=None,
            signature=Signature(algorithm="", value="", key_id=""),
            issued_at=datetime.now(timezone.utc),
        )
        with pytest.raises(AttestationNotAvailableError):
            a.verify(receipt)
