"""Verify that built distributions contain only publishable project files."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "live-output",
    "output",
}
FORBIDDEN_SUFFIXES = {
    ".agf",
    ".bak",
    ".constraints",
    ".ddp",
    ".dll",
    ".log",
    ".mf",
    ".pyc",
    ".tmp",
    ".zda",
    ".zmx",
    ".zos",
    ".zrd",
}
FORBIDDEN_FILENAMES = {
    ".coverage",
    ".env",
    "client.local.json",
    "config.local.json",
    "coverage-report.md",
    "coverage.xml",
    "offline-test-report.md",
}
ALLOWED_SDIST_ROOTS = {
    ".github",
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "CHANGELOG.md",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs",
    "examples",
    "live-test-report.md",
    "porting-notes.md",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
    "tool-coverage.json",
    "uv.lock",
}
REQUIRED_SDIST_PATHS = {
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "src/zemax_mcp/__init__.py",
}
LOCAL_PATH_PATTERNS = (
    re.compile(rb"[A-Za-z]:\\Test\\mcpPython", re.IGNORECASE),
    re.compile(rb"[A-Za-z]:/Test/mcpPython", re.IGNORECASE),
)
MAX_TEXT_SCAN_BYTES = 2_000_000


def _normalized(name: str) -> str:
    return name.replace("\\", "/").lstrip("./")


def _payload_root_and_relative(name: str) -> tuple[str, str]:
    normalized = _normalized(name)
    parts = PurePosixPath(normalized).parts
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], PurePosixPath(*parts[1:]).as_posix()


def _common_violations(names: Iterable[str]) -> list[str]:
    problems: list[str] = []
    for raw_name in names:
        name = _normalized(raw_name)
        path = PurePosixPath(name)
        if raw_name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw_name):
            problems.append(f"absolute archive member path: {raw_name}")
        if ".." in path.parts:
            problems.append(f"parent traversal in archive member: {raw_name}")
        lowered_parts = {part.lower() for part in path.parts}
        forbidden_parts = sorted(lowered_parts & FORBIDDEN_PARTS)
        if forbidden_parts:
            problems.append(f"forbidden path component {forbidden_parts[0]!r}: {raw_name}")
        filename = path.name.lower()
        if filename in FORBIDDEN_FILENAMES or filename.startswith(".env."):
            problems.append(f"forbidden filename: {raw_name}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"forbidden file extension: {raw_name}")
    return problems


def _scan_content(name: str, data: bytes) -> list[str]:
    if len(data) > MAX_TEXT_SCAN_BYTES or b"\x00" in data:
        return []
    return [
        f"machine-local project path found in {name}"
        for pattern in LOCAL_PATH_PATTERNS
        if pattern.search(data)
    ]


def _verify_wheel(path: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        problems.extend(_common_violations(names))
        if not any(_normalized(name).startswith("zemax_mcp/") for name in names):
            problems.append("wheel does not contain the zemax_mcp package")
        if not any(".dist-info/" in _normalized(name) for name in names):
            problems.append("wheel does not contain distribution metadata")
        for name in names:
            normalized = _normalized(name).lower()
            if normalized.startswith(("tests/", "docs/", "examples/", ".github/", "scripts/")):
                problems.append(f"repository-only content found in wheel: {name}")
            if not name.endswith("/"):
                problems.extend(_scan_content(name, archive.read(name)))
    return problems


def _verify_sdist(path: Path) -> list[str]:
    problems: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        names = [member.name for member in members]
        problems.extend(_common_violations(names))
        relative_names: set[str] = set()
        for member in members:
            _, relative = _payload_root_and_relative(member.name)
            if not relative:
                continue
            relative_names.add(relative)
            root = PurePosixPath(relative).parts[0]
            if root not in ALLOWED_SDIST_ROOTS:
                problems.append(f"unexpected source-distribution root {root!r}: {member.name}")
            extracted = archive.extractfile(member)
            if extracted is not None:
                problems.extend(_scan_content(member.name, extracted.read()))
        for required in sorted(REQUIRED_SDIST_PATHS - relative_names):
            problems.append(f"source distribution is missing required path: {required}")
    return problems


def _distribution_paths(directory: Path) -> tuple[list[Path], list[Path]]:
    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("*.tar.gz"))
    return wheels, sdists


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory containing wheel and sdist files")
    args = parser.parse_args(argv)

    wheels, sdists = _distribution_paths(args.directory)
    problems: list[str] = []
    if not wheels:
        problems.append(f"no wheel found in {args.directory}")
    if not sdists:
        problems.append(f"no source distribution found in {args.directory}")

    for path in wheels:
        problems.extend(f"{path.name}: {problem}" for problem in _verify_wheel(path))
    for path in sdists:
        problems.extend(f"{path.name}: {problem}" for problem in _verify_sdist(path))

    if problems:
        print("Distribution content verification failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print(f"Verified {len(wheels)} wheel(s) and {len(sdists)} source archive(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
