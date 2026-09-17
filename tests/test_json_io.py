from __future__ import annotations

from pathlib import Path

import pytest

from coador.render import json_io
from coador.render.json_io import atomic_write_text, write_json


def test_atomic_write_text_writes_utf8_content(tmp_path: Path) -> None:
    path = tmp_path / "output.txt"

    atomic_write_text(path, "Grüße, мир\n")

    assert path.read_text(encoding="utf-8") == "Grüße, мир\n"
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_text_cleans_up_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "output.txt"
    path.write_text("original", encoding="utf-8")

    def fail_replace(_source: str, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(json_io.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_write_json_preserves_existing_format(tmp_path: Path) -> None:
    path = tmp_path / "output.json"

    write_json(path, {"message": "Grüße", "enabled": True})

    assert path.read_text(encoding="utf-8") == '{\n  "message": "Grüße",\n  "enabled": true\n}\n'
