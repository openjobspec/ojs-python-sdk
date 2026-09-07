"""Smoke tests for executable documentation patterns."""

from __future__ import annotations

import inspect
from pathlib import Path

import ojs
from ojs.encryption import (
    EncryptionCodec,
    StaticKeyProvider,
    decryption_middleware,
    encryption_middleware,
)
from tests.conftest import FakeTransport


def test_python_examples_compile() -> None:
    examples = Path(__file__).parents[1] / "examples"

    for path in examples.glob("*.py"):
        compile(path.read_text(), str(path), "exec")


def test_middleware_docstrings_use_shipped_registration_apis() -> None:
    import ojs.encryption
    import ojs.middleware.logging
    import ojs.middleware.metrics
    import ojs.middleware.retry
    import ojs.middleware.timeout
    import ojs.otel

    modules = [
        ojs.encryption,
        ojs.middleware.logging,
        ojs.middleware.metrics,
        ojs.middleware.retry,
        ojs.middleware.timeout,
        ojs.otel,
    ]

    for module in modules:
        assert "add_middleware" not in (inspect.getdoc(module) or "")


def test_documented_encryption_middleware_registration() -> None:
    codec = EncryptionCodec(
        StaticKeyProvider(
            keys={"v1": b"x" * 32},
            current_key="v1",
        )
    )
    transport = FakeTransport()
    client = ojs.Client("https://ojs.example.com", transport=transport)
    worker = ojs.Worker("https://ojs.example.com", transport=transport)

    client.enqueue_middleware(encryption_middleware(codec))
    worker.middleware(decryption_middleware(codec))

    assert len(client._enqueue_middleware._middlewares) == 1
    assert len(worker._execution_middleware._middlewares) == 1
