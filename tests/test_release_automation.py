from __future__ import annotations

import json
from pathlib import Path

import ojs

ROOT = Path(__file__).resolve().parents[1]


def version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
    return int(parts[0]), int(parts[1]), int(parts[2])


def release_state(manifest_version: str, package_version: str) -> str:
    manifest_semver = version_tuple(manifest_version)
    package_semver = version_tuple(package_version)
    assert manifest_semver <= package_semver
    return "post-merge" if manifest_semver == package_semver else "pre-release"


def find_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(find_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(find_key(child, key) for child in value)
    return False


def test_release_please_accepts_monotonic_release_states() -> None:
    config = json.loads((ROOT / "release-please-config.json").read_text())
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
    package = config["packages"]["."]
    manifest_version = manifest["."]
    package_version = ojs.__version__

    assert package["release-type"] == "python"
    assert package["bump-minor-pre-major"] is True
    assert not find_key(config, "release-as")
    assert release_state(manifest_version, package_version) in {"pre-release", "post-merge"}
    assert release_state(package_version, package_version) == "post-merge"


def test_future_release_calculations_are_not_stuck() -> None:
    major, minor, patch = version_tuple(ojs.__version__)
    future_versions = (
        f"{major}.{minor}.{patch + 1}",
        f"{major}.{minor + 1}.0",
        f"{major + 1}.0.0",
    )

    for future_version in future_versions:
        assert release_state(ojs.__version__, future_version) == "pre-release"
        assert release_state(future_version, future_version) == "post-merge"

    try:
        release_state(future_versions[0], ojs.__version__)
    except AssertionError:
        pass
    else:
        raise AssertionError("backward semantic-version movement was accepted")
