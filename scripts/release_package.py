"""Build and validate the HACS release archive."""

from __future__ import annotations

import argparse
import compileall
import json
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "chore_race"
REQUIRED_FILES = {
    "__init__.py",
    "config_flow.py",
    "manifest.json",
    "services.yaml",
}
SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _source_files() -> list[Path]:
    """Return deterministic release contents without generated Python files."""
    return sorted(
        path
        for path in COMPONENT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def build_archive(output: Path) -> None:
    """Create a HACS zip whose root is the integration directory contents."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source in _source_files():
            archive.write(source, source.relative_to(COMPONENT).as_posix())
    validate_archive(output)


def validate_archive(archive_path: Path) -> None:
    """Reject incomplete, unsafe, or non-installable release archives."""
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Release archive contains duplicate paths")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe release path: {name}")
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                raise ValueError(f"Generated Python file in release: {name}")

        missing = REQUIRED_FILES - set(names)
        if missing:
            raise ValueError(f"Release archive is missing: {sorted(missing)}")

        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("domain") != "chore_race":
            raise ValueError("Release manifest has the wrong domain")
        version = manifest.get("version")
        if not isinstance(version, str) or not SEMANTIC_VERSION.fullmatch(version):
            raise ValueError("Release manifest version is not semantic")

        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = (
                Path(temp_dir)
                / "config"
                / "custom_components"
                / "chore_race"
            )
            install_dir.mkdir(parents=True)
            archive.extractall(install_dir)
            if not compileall.compile_dir(
                install_dir, quiet=1, force=True
            ):
                raise ValueError("Extracted integration does not compile")


def main() -> None:
    """Run the release package command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build_archive(args.archive)
    else:
        validate_archive(args.archive)
    print(f"{args.command} OK: {args.archive}")


if __name__ == "__main__":
    main()
