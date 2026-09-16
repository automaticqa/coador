from __future__ import annotations

from pathlib import Path

from coador.detectors.ui_testing import UITestFrameworkLocationDetector
from coador.fileindex import active_index, get_index, invalidate
from coador.fingerprint import collect_entries
from coador.repo import iter_files


def test_custom_exclusions_prune_only_paths_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    included = root / "app" / "src" / "Main.kt"
    excluded = root / "generated-kb"
    excluded_file = excluded / "nested" / "profile.json"
    included.parent.mkdir(parents=True)
    excluded_file.parent.mkdir(parents=True)
    included.write_text("class Main\n", encoding="utf-8")
    excluded_file.write_text("generated\n", encoding="utf-8")

    files = list(iter_files(root, excluded_paths=[excluded, tmp_path]))
    entries = collect_entries(root, excluded_paths=[excluded, tmp_path])

    assert files == [included]
    assert [entry.relative_path for entry in entries] == ["app/src/Main.kt"]


def test_indexed_directories_respect_exclusions_and_active_index(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    included = root / "app" / "src" / "androidTest"
    excluded = root / "generated-kb"
    excluded_android_test = excluded / "src" / "androidTest"
    included.mkdir(parents=True)
    excluded_android_test.mkdir(parents=True)
    invalidate(root)

    index = get_index(root, excluded_paths=[excluded, tmp_path, excluded])
    equivalent = get_index(root, excluded_paths=[tmp_path, excluded])
    token = active_index.set(index)
    try:
        active = get_index(root)
        detection = UITestFrameworkLocationDetector(root).detect()
    finally:
        active_index.reset(token)

    assert equivalent is index
    assert active is index
    assert index.find_dirs({"androidTest"}) == [included]
    assert excluded_android_test not in index.find_dirs({"androidTest"})
    assert detection.detected
    assert [evidence.file_path for evidence in detection.evidence] == ["app/src/androidTest"]
