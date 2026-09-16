from __future__ import annotations

import logging
from pathlib import Path

import pytest

from coador.repo import find_gradle_roots, find_repo_root


def _make_project(root: Path, name: str = "settings.gradle.kts") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text('rootProject.name = "x"\n', encoding="utf-8")
    return root


def test_finds_settings_in_the_given_directory(tmp_path: Path) -> None:
    _make_project(tmp_path)
    assert find_repo_root(tmp_path) == tmp_path


def test_finds_settings_in_a_child_directory(tmp_path: Path) -> None:
    child = _make_project(tmp_path / "checkout")
    assert find_repo_root(tmp_path) == child


def test_prefers_the_nearest_root_and_reports_the_others(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    near = _make_project(tmp_path / "app-repo")
    far = _make_project(tmp_path / "app-repo" / "samples" / "demo")

    with caplog.at_level(logging.WARNING, logger="coador.repo"):
        assert find_repo_root(tmp_path) == near

    assert str(far) in caplog.text
    assert find_gradle_roots(tmp_path) == [near, far]


def test_returns_none_without_any_gradle_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert find_repo_root(tmp_path) is None


def test_groovy_settings_file_is_recognised(tmp_path: Path) -> None:
    _make_project(tmp_path / "legacy", name="settings.gradle")
    assert find_repo_root(tmp_path) == tmp_path / "legacy"
