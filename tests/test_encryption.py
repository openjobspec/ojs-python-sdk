"""Tests for OJS encryption codec and middleware."""

from __future__ import annotations

import os

import pytest

cryptography = pytest.importorskip("cryptography", reason="cryptography package required")

from cryptography.exceptions import InvalidTag

from ojs.encryption import (
    ENCODING_ENCRYPTED,
    META_ENCODINGS,
    META_KEY_ID,
    META_NONCE,
    EncryptionCodec,
    StaticKeyProvider,
    decryption_middleware,
    encryption_middleware,
)
from ojs.job import Job, JobContext, JobRequest, JobState


def _make_provider(
    *,
    num_keys: int = 1,
    current_index: int = 0,
) -> tuple[StaticKeyProvider, list[tuple[str, bytes]]]:
    """Helper to create a StaticKeyProvider with random keys."""
    entries = [(f"k{i}", os.urandom(32)) for i in range(num_keys)]
    keys = dict(entries)
    provider = StaticKeyProvider(keys=keys, current_key=entries[current_index][0])
    return provider, entries


class TestEncryptionCodec:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        provider, _ = _make_provider()
        codec = EncryptionCodec(provider)
        plaintext = b"hello world"

        ciphertext, nonce, key_id = codec.encrypt(plaintext)
        result = codec.decrypt(ciphertext, nonce, key_id)

        assert result == plaintext

    def test_decrypt_wrong_key(self) -> None:
        provider_a, _ = _make_provider()
        provider_b, _ = _make_provider()
        codec_a = EncryptionCodec(provider_a)
        codec_b = EncryptionCodec(provider_b)

        ciphertext, nonce, key_id = codec_a.encrypt(b"secret")

        with pytest.raises(InvalidTag):
            codec_b.decrypt(ciphertext, nonce, key_id)

    def test_nonce_uniqueness(self) -> None:
        provider, _ = _make_provider()
        codec = EncryptionCodec(provider)
        plaintext = b"same input"

        ct1, nonce1, _ = codec.encrypt(plaintext)
        ct2, nonce2, _ = codec.encrypt(plaintext)

        assert nonce1 != nonce2
        assert ct1 != ct2

    def test_empty_plaintext(self) -> None:
        provider, _ = _make_provider()
        codec = EncryptionCodec(provider)

        ciphertext, nonce, key_id = codec.encrypt(b"")
        result = codec.decrypt(ciphertext, nonce, key_id)

        assert result == b""


class TestStaticKeyProvider:
    def test_returns_correct_key(self) -> None:
        key = os.urandom(32)
        provider = StaticKeyProvider(keys={"v1": key}, current_key="v1")

        assert provider.get_key("v1") == key
        assert provider.current_key_id() == "v1"

    def test_raises_for_unknown_id(self) -> None:
        provider = StaticKeyProvider(keys={"v1": os.urandom(32)}, current_key="v1")

        with pytest.raises(KeyError, match="unknown key ID"):
            provider.get_key("missing")

    def test_rejects_current_key_not_in_keys(self) -> None:
        with pytest.raises(ValueError, match="not found in keys"):
            StaticKeyProvider(keys={"v1": os.urandom(32)}, current_key="v2")

    def test_rejects_wrong_key_length(self) -> None:
        with pytest.raises(ValueError, match="must be 32 bytes"):
            StaticKeyProvider(keys={"v1": b"short"}, current_key="v1")


class TestCodecWithKeyRotation:
    def test_decrypt_with_old_key_after_rotation(self) -> None:
        key_old = os.urandom(32)
        key_new = os.urandom(32)

        provider_v1 = StaticKeyProvider(keys={"v1": key_old}, current_key="v1")
        codec_v1 = EncryptionCodec(provider_v1)
        ciphertext, nonce, key_id = codec_v1.encrypt(b"rotated secret")

        provider_v2 = StaticKeyProvider(
            keys={"v1": key_old, "v2": key_new}, current_key="v2"
        )
        codec_v2 = EncryptionCodec(provider_v2)

        result = codec_v2.decrypt(ciphertext, nonce, key_id)
        assert result == b"rotated secret"

    def test_new_encryptions_use_current_key(self) -> None:
        key_old = os.urandom(32)
        key_new = os.urandom(32)
        provider = StaticKeyProvider(
            keys={"v1": key_old, "v2": key_new}, current_key="v2"
        )
        codec = EncryptionCodec(provider)

        _, _, key_id = codec.encrypt(b"data")
        assert key_id == "v2"


class TestEncryptionMiddleware:
    async def test_meta_keys_set_after_encryption(self) -> None:
        provider, entries = _make_provider()
        codec = EncryptionCodec(provider)
        mw = encryption_middleware(codec)

        request = JobRequest(type="email", args=["alice", 42])
        captured_request: JobRequest | None = None

        async def final(req: JobRequest) -> Job:
            nonlocal captured_request
            captured_request = req
            return Job(id="j1", type=req.type, state=JobState.AVAILABLE, args=req.args)

        await mw(request, final)

        assert captured_request is not None
        meta = captured_request.meta
        assert meta is not None
        assert meta[META_ENCODINGS] == [ENCODING_ENCRYPTED]
        assert meta[META_KEY_ID] == entries[0][0]
        assert META_NONCE in meta

    async def test_encrypt_then_decrypt_via_middleware(self) -> None:
        provider, _ = _make_provider()
        codec = EncryptionCodec(provider)
        enc_mw = encryption_middleware(codec)
        dec_mw = decryption_middleware(codec)

        original_args = ["send_email", {"to": "bob@example.com"}]
        request = JobRequest(type="email", args=list(original_args))
        encrypted_job: Job | None = None

        async def enqueue_final(req: JobRequest) -> Job:
            nonlocal encrypted_job
            encrypted_job = Job(
                id="j1",
                type=req.type,
                state=JobState.ACTIVE,
                args=req.args,
                meta=req.meta,
            )
            return encrypted_job

        await enc_mw(request, enqueue_final)
        assert encrypted_job is not None
        assert encrypted_job.args != original_args

        ctx = JobContext(job=encrypted_job, attempt=1)
        decrypted_args: list | None = None

        async def worker_handler() -> None:
            nonlocal decrypted_args
            decrypted_args = list(ctx.job.args)

        await dec_mw(ctx, worker_handler)

        assert decrypted_args == original_args
