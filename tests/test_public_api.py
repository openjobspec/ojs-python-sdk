from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import ojs

EXPECTED_LAZY_MODULES = {
    "agent",
    "attest",
    "ml",
    "otel",
    "recorder",
    "serverless",
    "subscribe",
}


def test_runtime_version_matches_distribution_metadata() -> None:
    assert ojs.__version__ == version("openjobspec")


def test_documented_lazy_modules_are_public() -> None:
    assert set(ojs.__all__) >= EXPECTED_LAZY_MODULES
    for module_name in EXPECTED_LAZY_MODULES:
        module = getattr(ojs, module_name)
        assert module.__name__ == f"ojs.{module_name}"


def test_agent_durable_matches_documented_export() -> None:
    assert callable(ojs.agent.durable)


def test_every_public_export_resolves_in_fresh_process() -> None:
    script = (
        "import ojs\n"
        "missing = [name for name in ojs.__all__ if not hasattr(ojs, name)]\n"
        "assert not missing, missing\n"
        "assert ojs.agent.durable\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and constant script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_dir_contains_complete_public_surface() -> None:
    assert set(ojs.__all__) <= set(dir(ojs))


def test_file_to_package_facades_preserve_historical_imports() -> None:
    from ojs.client import JobRequest, RetryConfig, Transport
    from ojs.transport.http import RetryConfig as HTTPRetryConfig
    from ojs.transport.http import Transport as HTTPTransportProtocol

    assert JobRequest is ojs.JobRequest
    assert RetryConfig is HTTPRetryConfig
    assert Transport is HTTPTransportProtocol


def test_release_please_updates_runtime_version_source() -> None:
    repository = Path(__file__).resolve().parents[1]
    config = json.loads((repository / "release-please-config.json").read_text())
    package = config["packages"]["."]
    version_source = (repository / "src/ojs/_version.py").read_text()
    release_workflow = (repository / ".github/workflows/release.yml").read_text()

    assert "src/ojs/_version.py" in package["extra-files"]
    assert "x-release-please-version" in version_source
    assert "actual ==" in release_workflow
    assert "os.environ['RELEASE_TAG']" in release_workflow
