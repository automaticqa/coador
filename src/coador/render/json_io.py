"""Atomic reading and writing of the knowledge-base JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from coador.model import Profile, SchemaMismatchError
from coador.paths import checked_path, read_text


def atomic_write_text(path: Path, content: str) -> None:
    """Write UTF-8 ``content`` through a same-directory temporary file."""
    checked_path(path.parent, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` as pretty JSON, replacing ``path`` atomically."""
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    atomic_write_text(path, content)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning an empty mapping when it is missing or broken."""
    if not path.exists():
        return {}
    try:
        content = read_text(path.parent, path)
        if content is None:
            return {}
        data = json.loads(content)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_profile(path: Path, profile: Profile) -> None:
    write_json(path, profile.to_dict())


def read_profile(path: Path) -> Profile | None:
    data = read_json(path)
    if not data:
        return None
    try:
        return Profile.from_dict(data)
    except SchemaMismatchError:
        raise
    except (KeyError, TypeError, ValueError):
        return None
