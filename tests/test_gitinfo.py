from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import coador.gitinfo as gitinfo
from coador.gitinfo import (
    UNAVAILABLE,
    changed_files_since,
    normalize_git_object_id,
    read_git_info,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "initial")
    return tmp_path


def test_reads_commit_of_clean_tree(repo: Path) -> None:
    info = read_git_info(repo)
    assert info.available
    assert info.commit is not None
    assert len(info.commit) == 40
    assert info.dirty is False


def test_detects_dirty_tree(repo: Path) -> None:
    (repo / "settings.gradle.kts").write_text('rootProject.name = "y"\n', encoding="utf-8")
    info = read_git_info(repo)
    assert info.dirty is True


def test_counts_changed_files_since_commit(repo: Path) -> None:
    info = read_git_info(repo)
    assert info.commit is not None
    assert changed_files_since(repo, info.commit) == 0

    (repo / "settings.gradle.kts").write_text('rootProject.name = "y"\n', encoding="utf-8")
    assert changed_files_since(repo, info.commit) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("a" * 40, "a" * 40),
        ("A" * 40, "a" * 40),
        ("b" * 64, "b" * 64),
        ("B" * 64, "b" * 64),
    ],
)
def test_normalizes_complete_git_object_ids(value: object, expected: str | None) -> None:
    assert normalize_git_object_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "--output=/tmp/out",
        "-" + "a" * 39,
        "a" * 12,
        " " + "a" * 40,
        "a" * 40 + "\n",
        "a" * 20 + "\0" + "a" * 19,
        "g" * 40,
        "a" * 39,
        "a" * 41,
        123,
        True,
        [],
    ],
)
def test_rejects_invalid_git_object_ids(value: object) -> None:
    with pytest.raises(ValueError, match="Invalid Git object ID"):
        normalize_git_object_id(value)


def test_invalid_revision_never_reaches_git(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    def fail_if_called(_repo_root: Path, *_args: str) -> str | None:
        pytest.fail("invalid revision reached the Git subprocess boundary")

    monkeypatch.setattr(gitinfo, "_run_git", fail_if_called)
    assert changed_files_since(repo, "--output=/tmp/out") is None
    assert changed_files_since(repo, "a\0b") is None
    assert changed_files_since(repo, 123) is None


def test_shared_git_invocation_disables_helpers_and_optional_writes(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def completed(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs["env"]))
        if command[-2:] == ["rev-parse", "HEAD"]:
            stdout = "a" * 40 + "\n"
        elif command[-2:] == ["rev-parse", "--show-toplevel"]:
            stdout = f"{repo}\n"
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(gitinfo.subprocess, "run", completed)

    assert read_git_info(repo).commit == "a" * 40
    assert changed_files_since(repo, "B" * 40) == 0
    assert len(calls) == 4
    for command, environment in calls:
        assert command[:4] == ["git", "-c", "core.fsmonitor=false", "-C"]
        assert environment["GIT_OPTIONAL_LOCKS"] == "0"


def test_configured_fsmonitor_does_not_break_metadata_queries(repo: Path) -> None:
    missing_helper = repo / "missing-fsmonitor-helper"
    _git(repo, "config", "core.fsmonitor", str(missing_helper))

    info = read_git_info(repo)

    assert info.commit is not None
    assert info.dirty is False


def test_status_query_does_not_refresh_the_index(repo: Path) -> None:
    tracked = repo / "settings.gradle.kts"
    index = repo / ".git" / "index"
    before = index.read_bytes()
    stat = tracked.stat()
    os.utime(tracked, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))

    assert read_git_info(repo).dirty is False
    assert index.read_bytes() == before


def test_degrades_outside_a_work_tree(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert read_git_info(plain) == UNAVAILABLE


def test_reports_the_work_tree_root(repo: Path) -> None:
    info = read_git_info(repo)
    assert info.root is not None
    assert info.is_repository_root(repo)


def test_changes_are_scoped_to_the_given_directory(repo: Path) -> None:
    nested = repo / "vendored"
    nested.mkdir()
    (nested / "settings.gradle.kts").write_text('rootProject.name = "v"\n', encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "add vendored project")

    info = read_git_info(nested)
    assert info.commit is not None
    assert not info.is_repository_root(nested)

    (repo / "settings.gradle.kts").write_text('rootProject.name = "changed"\n', encoding="utf-8")
    assert changed_files_since(nested, info.commit) == 0
    assert changed_files_since(repo, info.commit) == 1
