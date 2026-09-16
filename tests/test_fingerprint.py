from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import coador.fingerprint as fingerprint_module
from coador.fingerprint import collect_entries, content_fingerprint, quick_fingerprint


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "gradle").mkdir()
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n', encoding="utf-8")
    (tmp_path / "gradle" / "libs.versions.toml").write_text("[versions]\n", encoding="utf-8")
    return tmp_path


def test_fingerprints_are_stable_for_an_unchanged_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = collect_entries(repo)
    second = collect_entries(repo)
    assert quick_fingerprint(first) == quick_fingerprint(second)
    assert content_fingerprint(first) == content_fingerprint(second)


def test_touching_a_file_changes_only_the_quick_fingerprint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = collect_entries(repo)
    quick_before = quick_fingerprint(before)
    content_before = content_fingerprint(before)

    target = repo / "settings.gradle.kts"
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns + 10**9, stat.st_mtime_ns + 10**9))

    after = collect_entries(repo)
    assert quick_fingerprint(after) != quick_before
    assert content_fingerprint(after) == content_before


def test_editing_a_file_changes_the_content_fingerprint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    content_before = content_fingerprint(collect_entries(repo))
    (repo / "settings.gradle.kts").write_text('rootProject.name = "y"\n', encoding="utf-8")
    assert content_fingerprint(collect_entries(repo)) != content_before


def test_editing_a_file_beyond_64_kib_changes_the_content_fingerprint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "large.kt"
    target.write_bytes(b"a" * (64 * 1024) + b"before")
    before_entries = collect_entries(repo)
    quick_before = quick_fingerprint(before_entries)
    content_before = content_fingerprint(before_entries)
    stat = target.stat()

    target.write_bytes(b"a" * (64 * 1024) + b"after!")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert target.stat().st_size == 64 * 1024 + len(b"before")
    after_entries = collect_entries(repo)
    assert quick_fingerprint(after_entries) == quick_before
    assert content_fingerprint(after_entries) != content_before


def test_quick_fingerprint_does_not_open_source_files(tmp_path: Path, monkeypatch) -> None:
    entries = collect_entries(_repo(tmp_path))
    open_source = Mock(side_effect=AssertionError("quick fingerprint read file content"))
    monkeypatch.setattr(fingerprint_module, "open_source", open_source)

    assert quick_fingerprint(entries)
    open_source.assert_not_called()


def test_large_tree_has_zero_quick_reads_and_one_full_read_per_file(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "large"
    repo.mkdir()
    for index in range(128):
        (repo / f"Source{index:03}.kt").write_text(f"class Source{index}\n", encoding="utf-8")
    entries = collect_entries(repo)
    real_open = fingerprint_module.open_source
    opened = Mock(wraps=real_open)
    monkeypatch.setattr(fingerprint_module, "open_source", opened)

    assert quick_fingerprint(entries)
    opened.assert_not_called()
    assert content_fingerprint(entries)
    assert opened.call_count == len(entries) == 128


def test_knowledge_base_directory_is_not_part_of_the_fingerprint(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = quick_fingerprint(collect_entries(repo))

    kb = repo / ".coador"
    kb.mkdir()
    (kb / "manifest.json").write_text("{}", encoding="utf-8")

    assert quick_fingerprint(collect_entries(repo)) == before
