"""Deterministic lazy export registry for optional features and submodules."""

from __future__ import annotations

from types import MappingProxyType

LAZY_ATTRIBUTES = MappingProxyType(
    {
        "EncryptionCodec": ("ojs.encryption", "EncryptionCodec"),
        "StaticKeyProvider": ("ojs.encryption", "StaticKeyProvider"),
        "decryption_middleware": ("ojs.encryption", "decryption_middleware"),
        "encryption_middleware": ("ojs.encryption", "encryption_middleware"),
    }
)

LAZY_MODULES = MappingProxyType(
    {
        "agent": "ojs.agent",
        "attest": "ojs.attest",
        "ml": "ojs.ml",
        "otel": "ojs.otel",
        "recorder": "ojs.recorder",
        "serverless": "ojs.serverless",
        "subscribe": "ojs.subscribe",
    }
)

__all__ = ["LAZY_ATTRIBUTES", "LAZY_MODULES"]
