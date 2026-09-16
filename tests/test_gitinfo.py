from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from coador.gitinfo import UNAVAILABLE, changed_files_since, read_git_info

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
