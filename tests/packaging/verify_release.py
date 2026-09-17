"""Verify public release archive structure and metadata without extracting it."""

from __future__ import annotations

import argparse
import json
import re
import stat
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

LOCAL_ONLY_PARTS = {
    ".agents",
    ".coador",
    ".claude",
    ".codex",
    ".mcp.json",
    "AGENTS.md",
    "AGENTS.override.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "CODEX_HANDOFF.md",
    "ROADMAP.md",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".env",
}

WHEEL_RUNTIME_FILES = {
    "coador/data/coador_probe.gradle",
    "coador/py.typed",
}

SDIST_PUBLIC_FILES = {
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "server.json",
    "SECURITY.md",
    "docs/adoption.md",
    "docs/contributor-tasks.md",
    "docs/detectors.md",
    "docs/mcp.md",
    "docs/onboarding-recipes.md",
    "docs/releases/0.1.0.md",
    "examples/README.md",
    "tests/fixtures/mini_android/settings.gradle.kts",
    "pyproject.toml",
    "src/coador/data/coador_probe.gradle",
    "src/coador/py.typed",
    "tests/test_mcp_stdio.py",
}

MCP_MARKER = b"<!-- mcp-name: io.github.automaticqa/coador -->"

EXPECTED_ENTRY_POINTS = {
    "coador = coador.cli:main",
    "coador-mcp = coador.mcp_server:main",
}

HIGH_CONFIDENCE_CREDENTIALS = {
    "local home path": re.compile(rb"/home/[A-Za-z0-9_.-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+\\"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{20,}"),
    "JWT": re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Slack token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
}
SYNTHETIC_CREDENTIAL_FIXTURE = "tests/test_redact.py"


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise AssertionError(f"unsafe archive member: {name!r}")
    if LOCAL_ONLY_PARTS.intersection(path.parts):
        raise AssertionError(f"local-only file leaked into release archive: {name}")
    if path.suffix in {".pyc", ".pyo", ".log", ".tmp", ".bak"}:
        raise AssertionError(f"generated file leaked into release archive: {name}")
    return path


def _read_wheel(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        result: dict[str, bytes] = {}
        for info in archive.infolist():
            member = _safe_member(info.filename)
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise AssertionError(f"wheel contains a symbolic link: {info.filename}")
            result[str(member)] = archive.read(info)
    return result


def _read_sdist(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, mode="r:gz") as archive:
        result: dict[str, bytes] = {}
        for info in archive.getmembers():
            member = _safe_member(info.name)
            if info.isdir():
                continue
            if not info.isfile():
                raise AssertionError(f"sdist contains a non-file member: {info.name}")
            extracted = archive.extractfile(info)
            assert extracted is not None
            result[str(member)] = extracted.read()
    return result


def _one_matching(files: Mapping[str, bytes], suffix: str) -> tuple[str, bytes]:
    matches = [(name, content) for name, content in files.items() if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(f"expected one {suffix}, found {[name for name, _ in matches]}")
    return matches[0]


def _metadata_version(metadata: bytes) -> str:
    if MCP_MARKER not in metadata:
        raise AssertionError("package long description is missing MCP ownership marker")
    text = metadata.decode("utf-8")
    required = {
        "Name: coador",
        "License: MIT",
        "License-File: LICENSE",
        "Requires-Python: >=3.11",
        "Requires-Dist: mcp<3,>=2.2",
    }
    missing = sorted(value for value in required if value not in text)
    if missing:
        raise AssertionError(f"package metadata is missing: {missing}")
    match = re.search(r"(?m)^Version: ([^\s]+)$", text)
    if match is None:
        raise AssertionError("package metadata has no version")
    version = match.group(1)
    if version != "0.1.0":
        raise AssertionError(f"unexpected release version: {version}")
    return version


def _assert_no_private_markers(files: Mapping[str, bytes]) -> None:
    forbidden = {
        b"BEGIN OPENSSH " + b"PRIVATE KEY",
        b"BEGIN RSA " + b"PRIVATE KEY",
    }
    for name, content in files.items():
        for marker in forbidden:
            if marker in content:
                raise AssertionError(f"private marker {marker!r} found in {name}")
        if name == SYNTHETIC_CREDENTIAL_FIXTURE:
            continue
        for label, pattern in HIGH_CONFIDENCE_CREDENTIALS.items():
            if pattern.search(content):
                raise AssertionError(f"{label} pattern found in {name}")


def verify_wheel(path: Path) -> str:
    files = _read_wheel(path)
    names = set(files)
    unexpected = sorted(
        name for name in names if not name.startswith("coador/") and ".dist-info/" not in name
    )
    if unexpected:
        raise AssertionError(f"unexpected wheel members: {unexpected}")
    missing_runtime = sorted(WHEEL_RUNTIME_FILES - names)
    if missing_runtime:
        raise AssertionError(f"wheel is missing runtime data: {missing_runtime}")

    metadata_name, metadata = _one_matching(files, ".dist-info/METADATA")
    version = _metadata_version(metadata)
    expected_dist_info = f"coador-{version}.dist-info/"
    if not metadata_name.startswith(expected_dist_info):
        raise AssertionError(f"metadata path does not match version {version}: {metadata_name}")

    _, entry_points = _one_matching(files, ".dist-info/entry_points.txt")
    entry_point_lines = set(entry_points.decode("utf-8").splitlines())
    if not entry_point_lines >= EXPECTED_ENTRY_POINTS:
        raise AssertionError("console entry points are incomplete")
    _one_matching(files, ".dist-info/licenses/LICENSE")
    _one_matching(files, ".dist-info/RECORD")
    _assert_no_private_markers(files)
    return version


def verify_sdist(path: Path) -> str:
    files = _read_sdist(path)
    roots = {PurePosixPath(name).parts[0] for name in files}
    if len(roots) != 1:
        raise AssertionError(f"sdist must have one root directory: {sorted(roots)}")
    root = next(iter(roots))
    prefix = f"{root}/"
    relative = {name.removeprefix(prefix): content for name, content in files.items()}

    _, metadata = _one_matching(relative, "PKG-INFO")
    version = _metadata_version(metadata)
    if root != f"coador-{version}":
        raise AssertionError(f"sdist root does not match version {version}: {root}")
    missing_public = sorted(SDIST_PUBLIC_FILES - set(relative))
    if missing_public:
        raise AssertionError(f"sdist is missing public files: {missing_public}")

    if MCP_MARKER not in relative["README.md"]:
        raise AssertionError("sdist README is missing MCP ownership marker")
    verify_server(relative["server.json"], version)

    examples_readme = relative["examples/README.md"].decode("utf-8")
    if "12f80da6518e161ed16a06a68e71fb8a873576d6" not in examples_readme:
        raise AssertionError("public example source revision is missing")
    if "Apache-2.0" not in examples_readme:
        raise AssertionError("public example attribution is missing")
    _assert_no_private_markers(relative)
    return version


def verify_server(content: bytes, version: str) -> None:
    server = json.loads(content)
    assert server["name"] == "io.github.automaticqa/coador"
    assert server["version"] == version
    assert len(server["packages"]) == 1
    package = server["packages"][0]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == "coador"
    assert package["version"] == version
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    command, repo = package["packageArguments"]
    assert command == {"type": "positional", "value": "mcp"}
    assert repo["type"] == "named" and repo["name"] == "--repo"
    assert repo["isRequired"] is True and repo["format"] == "filepath"
    assert "value" not in repo, "repository path must remain configurable"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-tag")
    parser.add_argument("sdist", type=Path)
    parser.add_argument("wheel", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sdist_version = verify_sdist(args.sdist)
    wheel_version = verify_wheel(args.wheel)
    repository_server = Path(__file__).resolve().parents[2] / "server.json"
    verify_server(repository_server.read_bytes(), wheel_version)
    if sdist_version != wheel_version:
        raise AssertionError(f"sdist/wheel version mismatch: {sdist_version} != {wheel_version}")
    if args.expected_tag is not None and args.expected_tag != f"v{wheel_version}":
        raise AssertionError(
            f"release tag/version mismatch: {args.expected_tag} != v{wheel_version}"
        )
    print(f"Release archives verified: coador {wheel_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
