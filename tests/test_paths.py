from __future__ import annotations

from pathlib import Path

import pytest

from coador.fileindex import FileIndex
from coador.fingerprint import collect_entries, content_fingerprint
from coador.paths import UnsafePathError, checked_path, normalize_reference, read_text
from coador.repo import find_dirs, iter_files


@pytest.mark.parametrize(
    "value",
    [
        "/etc/passwd",
        "../outside",
        "a/../../b",
        "C:/secret",
        "C:secret",
        r"\\server\share\secret",
        r"a\..\secret",
        "\x00bad",
        "a\nfile",
    ],
)
def test_unsafe_references_are_rejected(value: str) -> None:
    with pytest.raises(UnsafePathError):
        normalize_reference(value)


def test_relative_references_have_posix_spelling(tmp_path: Path) -> None:
    assert normalize_reference(r"app\src\Main.kt") == "app/src/Main.kt"
    assert normalize_reference("./app//Main.kt") == "app/Main.kt"
    with pytest.raises(UnsafePathError):
        normalize_reference(".")
    assert normalize_reference(".", directory=True) == "."
    with pytest.raises(UnsafePathError):
        checked_path(tmp_path, tmp_path.parent / "outside")


@pytest.mark.parametrize("internal", [True, False])
def test_links_are_not_discovered_read_or_fingerprinted(tmp_path: Path, internal: bool) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = (root if internal else tmp_path) / "target"
    target.mkdir()
    secret = target / "secret.kt"
    secret.write_text("outside_canary", encoding="utf-8")
    try:
        (root / "file.kt").symlink_to(secret)
        (root / "linked").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    assert root / "file.kt" not in list(iter_files(root))
    assert root / "linked" not in find_dirs(root, ["linked"])
    assert read_text(root, root / "file.kt") is None
    assert read_text(root, root / "linked" / "secret.kt") is None
    index = FileIndex.build(root)
    assert index.read(root / "file.kt") is None
    entries = collect_entries(root)
    assert all("linked" not in e.relative_path and e.relative_path != "file.kt" for e in entries)
    assert content_fingerprint(entries)


def test_index_cannot_read_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.kt"
    outside.write_text("canary", encoding="utf-8")
    index = FileIndex.build(root)
    assert index.read(outside) is None
    with pytest.raises(UnsafePathError):
        index.relative(outside)


def test_index_reads_an_indexed_file_from_a_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    source = root / "app" / "src" / "Main.kt"
    source.parent.mkdir(parents=True)
    source.write_text("class Main\n", encoding="utf-8")

    index = FileIndex.build(root)

    assert index.read(Path("app/src/Main.kt")) == "class Main\n"


def test_fingerprint_rechecks_a_replaced_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    path = root / "file.kt"
    path.write_text("safe", encoding="utf-8")
    entries = collect_entries(root)
    outside = tmp_path / "outside"
    outside.write_text("canary", encoding="utf-8")
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    first = content_fingerprint(entries)
    outside.write_text("changed canary", encoding="utf-8")
    assert content_fingerprint(entries) == first
