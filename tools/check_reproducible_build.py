"""Build the package twice and verify byte-for-byte reproducibility."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_CONSTRAINTS = PROJECT_ROOT / "build-constraints.txt"
SOURCE_DATE_EPOCH = "1704067200"


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_contents(path: Path) -> dict[str, str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {
                name: hashlib.sha256(archive.read(name)).hexdigest()
                for name in sorted(archive.namelist())
                if not name.endswith("/")
            }
    with tarfile.open(path, mode="r:gz") as archive:
        contents: dict[str, str] = {}
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"could not read {member.name} from {path.name}")
            contents[member.name] = hashlib.sha256(extracted.read()).hexdigest()
        return contents


def _build(output: Path) -> list[Path]:
    environment = {**os.environ, "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        raise RuntimeError("uv is required to verify reproducible builds")
    subprocess.run(  # noqa: S603 - fixed uv executable and controlled arguments
        [
            uv_executable,
            "build",
            "--clear",
            "--no-build-logs",
            "--no-create-gitignore",
            "--no-sources",
            "--build-constraints",
            str(BUILD_CONSTRAINTS),
            "--out-dir",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    return sorted(
        path for path in output.iterdir() if path.suffix == ".whl" or path.name.endswith(".tar.gz")
    )


def verify_reproducible_build(output_dir: Path) -> None:
    """Build twice, compare artifact hashes and contents, and retain one build."""
    with tempfile.TemporaryDirectory(prefix="ojs-build-") as temporary:
        root = Path(temporary)
        first = _build(root / "first")
        second = _build(root / "second")
        if [path.name for path in first] != [path.name for path in second]:
            raise RuntimeError("repeated builds produced different artifact names")

        for first_path, second_path in zip(first, second, strict=True):
            first_contents = _archive_contents(first_path)
            second_contents = _archive_contents(second_path)
            if first_contents != second_contents:
                raise RuntimeError(
                    f"{first_path.name} contains different files or payloads across builds"
                )
            first_digest = _digest(first_path)
            second_digest = _digest(second_path)
            if first_digest != second_digest:
                raise RuntimeError(
                    f"{first_path.name} content matches but archive hashes differ: "
                    f"{first_digest} != {second_digest}"
                )
            print(f"{first_path.name}: sha256:{first_digest}")  # noqa: T201

        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        for artifact in first:
            shutil.copy2(artifact, output_dir / artifact.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
    )
    arguments = parser.parse_args()
    verify_reproducible_build(arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
