from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

VERIFY = runpy.run_path("tests/packaging/verify_release.py")


def test_registry_metadata_matches_release() -> None:
    VERIFY["verify_server"](Path("server.json").read_bytes(), "0.1.0")


@pytest.mark.parametrize("field", ["version", "identifier", "command", "repository"])
def test_registry_metadata_rejects_broken_invocation_or_identity(field: str) -> None:
    server = json.loads(Path("server.json").read_bytes())
    package = server["packages"][0]
    if field == "version":
        server["version"] = "0.2.0"
    elif field == "identifier":
        package["identifier"] = "coador-mcp"
    elif field == "command":
        package["packageArguments"][0]["value"] = "scan"
    else:
        package["packageArguments"][1]["value"] = "/fixed/repository"
    with pytest.raises(AssertionError):
        VERIFY["verify_server"](json.dumps(server).encode(), "0.1.0")


def test_packaged_description_requires_ownership_marker() -> None:
    metadata = b"\n".join(
        [
            b"Name: coador",
            b"Version: 0.1.0",
            b"License: MIT",
            b"License-File: LICENSE",
            b"Requires-Python: >=3.11",
            b"Requires-Dist: mcp<3,>=2.2",
            b"",
            b"# Coador",
        ]
    )
    with pytest.raises(AssertionError, match="ownership marker"):
        VERIFY["_metadata_version"](metadata)
    assert VERIFY["_metadata_version"](metadata + b"\n" + VERIFY["MCP_MARKER"]) == "0.1.0"
