"""OJS encryption middleware for client-side job arg encryption.

Encrypts job arguments before enqueue and decrypts them in the worker,
ensuring sensitive data is never stored in plaintext in the backend.

Uses AES-256-GCM via the ``cryptography`` library.

Usage::

    from ojs.encryption import (
        StaticKeyProvider,
        EncryptionCodec,
        encryption_middleware,
        decryption_middleware,
    )

    key = os.urandom(32)  # AES-256 requires 32 bytes
    provider = StaticKeyProvider(keys={"v1": key}, current_key="v1")
    codec = EncryptionCodec(provider)

    # Client side
    client = ojs.Client("http://localhost:8080")
    client.add_middleware(encryption_middleware(codec))

    # Worker side
    worker = ojs.Worker("http://localhost:8080", queues=["default"])
    worker.add_middleware(decryption_middleware(codec))
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ojs.job import Job, JobContext, JobRequest
from ojs.middleware import EnqueueMiddleware, EnqueueNext, ExecutionMiddleware, ExecutionNext

# Metadata keys (OJS codec spec).
META_ENCODINGS = "ojs.codec.encodings"
META_KEY_ID = "ojs.codec.key_id"
META_NONCE = "ojs.codec.nonce"

ENCODING_ENCRYPTED = "binary/encrypted"

# Legacy meta keys (pre-spec) — checked during decryption for backward compat.
_LEGACY_META_ENCRYPTED = "ojs_encoded"
_LEGACY_META_KEY_ID = "ojs_key_id"
_LEGACY_META_NONCE = "ojs_nonce"
_NONCE_BYTES = 12
_KEY_BYTES = 32


class KeyProvider(ABC):
    """Interface for supplying encryption keys.

    Implement this to integrate with external key management services
    (e.g. AWS KMS, HashiCorp Vault) or to support key rotation.
    """

    @abstractmethod
    def get_key(self, key_id: str) -> bytes:
        """Return the raw key bytes for the given key ID.

        Args:
            key_id: Identifier of the requested key.

        Returns:
            Raw 32-byte AES-256 key.

        Raises:
            KeyError: If the key ID is unknown.
        """

    @abstractmethod
    def current_key_id(self) -> str:
        """Return the key ID that should be used for new encryptions."""


class StaticKeyProvider(KeyProvider):
    """In-memory key provider backed by a fixed dictionary.

    Useful for testing or simple deployments without an external KMS.

    Args:
        keys: Mapping of key IDs to raw 32-byte AES-256 keys.
        current_key: The key ID to use for new encryptions.

    Raises:
        ValueError: If *current_key* is not present in *keys* or any
            key is not exactly 32 bytes.
    """

    def __init__(self, keys: dict[str, bytes], current_key: str) -> None:
        if current_key not in keys:
            raise ValueError(f"current_key {current_key!r} not found in keys")
        for kid, k in keys.items():
            if len(k) != _KEY_BYTES:
                raise ValueError(
                    f"key {kid!r} must be {_KEY_BYTES} bytes for AES-256 (got {len(k)})"
                )
        self._keys = dict(keys)
        self._current_key = current_key

    def get_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise KeyError(f"unknown key ID: {key_id!r}") from None

    def current_key_id(self) -> str:
        return self._current_key


class EncryptionCodec:
    """AES-256-GCM encryption codec for OJS job arguments.

    Args:
        key_provider: Supplies encryption keys and the current key ID.
    """

    def __init__(self, key_provider: KeyProvider) -> None:
        self._provider = key_provider

    def encrypt(self, plaintext: bytes) -> tuple[bytes, bytes, str]:
        """Encrypt *plaintext* with the current key.

        Args:
            plaintext: Data to encrypt.

        Returns:
            A tuple of ``(ciphertext, nonce, key_id)``.
        """
        key_id = self._provider.current_key_id()
        key = self._provider.get_key(key_id)
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
        return ciphertext, nonce, key_id

    def decrypt(self, ciphertext: bytes, nonce: bytes, key_id: str) -> bytes:
        """Decrypt *ciphertext* using the key identified by *key_id*.

        Args:
            ciphertext: The encrypted data (includes GCM auth tag).
            nonce: The 12-byte nonce used during encryption.
            key_id: Identifies which key to use for decryption.

        Returns:
            The original plaintext bytes.

        Raises:
            KeyError: If *key_id* is unknown.
            cryptography.exceptions.InvalidTag: If decryption fails
                (wrong key, tampered data, etc.).
        """
        key = self._provider.get_key(key_id)
        return AESGCM(key).decrypt(nonce, ciphertext, None)


def encryption_middleware(codec: EncryptionCodec) -> EnqueueMiddleware:
    """Return enqueue middleware that encrypts job args before sending.

    The original ``args`` list is JSON-serialised, encrypted, and replaced
    with a single-element list containing the base64-encoded ciphertext.
    Encryption metadata (codec name, key ID, nonce) is stored in
    ``request.meta`` so the worker can decrypt later.

    Args:
        codec: The encryption codec to use.

    Returns:
        An async enqueue middleware function.
    """

    async def _encrypt_mw(request: JobRequest, next_fn: EnqueueNext) -> Job | None:
        plaintext = json.dumps(request.args).encode("utf-8")
        ciphertext, nonce, key_id = codec.encrypt(plaintext)

        request.args = [base64.b64encode(ciphertext).decode("ascii")]

        if request.meta is None:
            request.meta = {}
        request.meta[META_ENCODINGS] = [ENCODING_ENCRYPTED]
        request.meta[META_KEY_ID] = key_id
        request.meta[META_NONCE] = base64.b64encode(nonce).decode("ascii")

        return await next_fn(request)

    return _encrypt_mw


def decryption_middleware(codec: EncryptionCodec) -> ExecutionMiddleware:
    """Return worker middleware that decrypts encrypted job args.

    Checks ``ojs.codec.encodings`` for ``"binary/encrypted"``. Also
    supports legacy ``ojs_encoded`` key for backward compatibility.

    Jobs that are not encrypted pass through unchanged.

    Args:
        codec: The encryption codec to use.

    Returns:
        An async execution middleware function.
    """

    async def _decrypt_mw(ctx: JobContext, next_fn: ExecutionNext) -> Any:
        meta = ctx.job.meta
        if not meta:
            return await next_fn()

        # Detect encryption via new spec keys or legacy keys.
        encodings = meta.get(META_ENCODINGS)
        is_encrypted = (
            isinstance(encodings, list) and ENCODING_ENCRYPTED in encodings
        ) or meta.get(_LEGACY_META_ENCRYPTED)

        if not is_encrypted:
            return await next_fn()

        if not ctx.job.args:
            return await next_fn()

        encoded_ciphertext = ctx.job.args[0]
        if not isinstance(encoded_ciphertext, str):
            return await next_fn()

        key_id = meta.get(META_KEY_ID) or meta.get(_LEGACY_META_KEY_ID, "")
        nonce_b64 = meta.get(META_NONCE) or meta.get(_LEGACY_META_NONCE, "")

        ciphertext = base64.b64decode(encoded_ciphertext)
        nonce = base64.b64decode(nonce_b64)

        plaintext = codec.decrypt(ciphertext, nonce, key_id)
        ctx.job.args = json.loads(plaintext)

        return await next_fn()

    return _decrypt_mw
