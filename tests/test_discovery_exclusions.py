from __future__ import annotations

from pathlib import Path

from coador.catalog import load_catalog
from coador.detectors.ui_testing import UITestFrameworkLocationDetector
from coador.fileindex import active_index, get_index, invalidate
from coador.fingerprint import collect_entries, content_fingerprint
from coador.repo import iter_files
from coador.scanner import read_project_name, scan
from coador.textscan import read_file_content, read_lines


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


def test_direct_reads_cannot_bypass_index_exclusions(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    included = root / "included.kt"
    excluded = root / "excluded.kt"
    fixed_exclusion = root / "excluded.png"
    build_src = root / "buildSrc"
    included.write_text("included\n", encoding="utf-8")
    excluded.write_text("excluded\n", encoding="utf-8")
    fixed_exclusion.write_text("fixed exclusion\n", encoding="utf-8")
    build_src.mkdir()

    index = get_index(root, excluded_paths=[excluded])
    token = active_index.set(index)
    try:
        detector = UITestFrameworkLocationDetector(root)

        assert excluded not in index.paths
        assert fixed_exclusion not in index.paths
        assert index.read(excluded) is None
        assert index.read(fixed_exclusion) is None
        assert read_file_content(excluded, root=root) is None
        assert read_lines(excluded, root=root) == []
        assert detector.read_file(excluded) is None
        assert detector.find_file("excluded.kt") is None
        assert detector.find_file("buildSrc") == build_src
        assert index.read(included) == "included\n"
        assert read_file_content(included, root=root) == "included\n"
    finally:
        active_index.reset(token)


def test_known_paths_use_active_index_scope(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    catalog_path = root / "gradle" / "libs.versions.toml"
    settings = root / "settings.gradle.kts"
    catalog_path.parent.mkdir(parents=True)
    settings.write_text('rootProject.name = "excluded-name"\n', encoding="utf-8")
    catalog_path.write_text('[versions]\nkotlin = "2.0.0"\n', encoding="utf-8")

    excluded_index = get_index(root, excluded_paths=[settings, catalog_path])
    token = active_index.set(excluded_index)
    try:
        detector = UITestFrameworkLocationDetector(root)
        assert read_project_name(root) == root.name
        assert load_catalog(root) is None
        assert detector.find_file("settings.gradle.kts") is None
        assert detector.find_file("gradle/libs.versions.toml") is None
    finally:
        active_index.reset(token)

    included_index = get_index(root)
    token = active_index.set(included_index)
    try:
        catalog = load_catalog(root)
        assert read_project_name(root) == "excluded-name"
        assert catalog is not None
        assert catalog.versions == {"kotlin": "2.0.0"}
        assert included_index.find("settings.gradle.kts") == settings
        assert included_index.find("gradle/libs.versions.toml") == catalog_path
    finally:
        active_index.reset(token)


def test_excluded_known_file_cannot_change_profile_outside_fingerprint_scope(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    settings = root / "settings.gradle.kts"
    settings.write_text('rootProject.name = "first-hidden-name"\n', encoding="utf-8")
    exclusions = (settings,)

    entries_before = collect_entries(root, excluded_paths=exclusions)
    profile_before = scan(root, excluded_paths=exclusions)
    settings.write_text('rootProject.name = "second-hidden-name"\n', encoding="utf-8")
    entries_after = collect_entries(root, excluded_paths=exclusions)
    profile_after = scan(root, excluded_paths=exclusions)

    assert content_fingerprint(entries_before) == content_fingerprint(entries_after)
    assert profile_before.project_name == profile_after.project_name == root.name
    assert profile_before.to_dict() == profile_after.to_dict()
