from __future__ import annotations

import builtins
import subprocess
import sys

import pytest

import ojs


def test_base_import_does_not_import_cryptography() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ojs; "
            "assert not any(name == 'cryptography' or name.startswith('cryptography.') "
            "for name in sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_encryption_dependency_error_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codec_type = ojs.EncryptionCodec
    provider_type = ojs.StaticKeyProvider
    real_import = builtins.__import__

    def guarded_import(
        name: str,
        globals_arg: dict[str, object] | None = None,
        locals_arg: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("cryptography"):
            raise ModuleNotFoundError(name)
        return real_import(name, globals_arg, locals_arg, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    provider = provider_type({"v1": b"x" * 32}, current_key="v1")

    with pytest.raises(ImportError, match=r"openjobspec\[crypto\]"):
        codec_type(provider)


def test_grpc_dependency_error_is_actionable_in_base_install_shape() -> None:
    script = """
import builtins

real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "grpc" or name.startswith("google.protobuf"):
        raise ModuleNotFoundError(name, name=name)
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
try:
    from ojs.transport.grpc import GrpcTransport
except ImportError as exc:
    assert "openjobspec[grpc]" in str(exc)
else:
    raise AssertionError(GrpcTransport)
"""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and local constant script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
