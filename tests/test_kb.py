from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from coador.gitinfo import GitInfo
from coador.kb import KnowledgeBase, State
from coador.model import SCHEMA_VERSION


def test_status_is_missing_before_the_first_scan(kb: KnowledgeBase) -> None:
    status = kb.status()
    assert status.state is State.MISSING
    assert status.needs_refresh
    assert "run `coador scan`" in status.describe()


def test_refresh_writes_manifest_profile_and_layers(kb: KnowledgeBase) -> None:
    status = kb.refresh()

    assert status.state is State.FRESH
    assert kb.manifest_path.exists()
    assert kb.profile_path.exists()
    assert len(list(kb.layers_dir.glob("*.md"))) == 9

    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["fingerprint_quick"] and manifest["fingerprint_content"]
    assert manifest["files_count"] == status.files_count


def test_second_refresh_is_a_no_op(kb: KnowledgeBase) -> None:
    kb.refresh()
    before = _snapshot(kb)

    kb.refresh()
    assert _snapshot(kb) == before


def test_editing_a_file_makes_the_knowledge_base_stale(kb: KnowledgeBase) -> None:
    kb.refresh()
    assert kb.status().state is State.FRESH

    (kb.repo_root / "settings.gradle.kts").write_text(
        'rootProject.name = "renamed"\n', encoding="utf-8"
    )
    assert kb.status().state is State.STALE

    kb.refresh()
    assert kb.status().state is State.FRESH
    profile = kb.require_profile()
    assert profile.project_name == "renamed"


def test_schema_mismatch_is_reported(kb: KnowledgeBase) -> None:
    kb.refresh()
    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = SCHEMA_VERSION + 1
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kb.status()
    assert status.state is State.SCHEMA_MISMATCH
    assert "coador scan" in status.describe()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_option_like_manifest_commit_cannot_write_outside_kb(
    kb: KnowledgeBase, tmp_path: Path
) -> None:
    subprocess.run(["git", "-C", str(kb.repo_root), "init", "--quiet"], check=True)
    subprocess.run(
        ["git", "-C", str(kb.repo_root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(kb.repo_root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(kb.repo_root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(kb.repo_root), "commit", "--quiet", "-m", "initial"], check=True
    )
    kb.refresh()
    marker = tmp_path / "outside-marker"
    marker.write_text("sentinel", encoding="utf-8")
    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = f"--output={marker}"
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status = kb.status()

    assert status.state is State.DAMAGED
    assert status.reason == "Git commit is invalid"
    assert marker.read_text(encoding="utf-8") == "sentinel"


@pytest.mark.parametrize("schema_mismatch", [False, True])
def test_invalid_manifest_commit_never_reaches_diff_on_error_paths(
    kb: KnowledgeBase,
    monkeypatch: pytest.MonkeyPatch,
    schema_mismatch: bool,
) -> None:
    kb.refresh()
    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = "--output=/tmp/should-not-exist"
    if schema_mismatch:
        manifest["schema_version"] = SCHEMA_VERSION + 1
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("coador.kb.read_git_info", lambda _root: GitInfo("a" * 40, False))

    def fail_if_called(_root: Path, _commit: object) -> int | None:
        pytest.fail("invalid persisted commit reached changed_files_since")

    monkeypatch.setattr("coador.kb.changed_files_since", fail_if_called)

    status = kb.status()
    assert status.state is (State.SCHEMA_MISMATCH if schema_mismatch else State.DAMAGED)
    with pytest.raises(FileNotFoundError):
        kb.load()


def test_refresh_rebuilds_cache_with_invalid_manifest_commit(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = "--output=/tmp/should-not-exist"
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fail_if_called(_root: Path, _commit: object) -> int | None:
        pytest.fail("invalid persisted commit reached changed_files_since")

    monkeypatch.setattr("coador.kb.changed_files_since", fail_if_called)

    status = kb.refresh()
    assert status.state is State.FRESH
    assert status.refresh_action == "scanned"


def test_uppercase_manifest_commit_is_normalized_before_diff(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    manifest = json.loads(kb.manifest_path.read_text(encoding="utf-8"))
    manifest["git_commit"] = "A" * 40
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("coador.kb.read_git_info", lambda _root: GitInfo("b" * 40, False))
    observed: list[object] = []

    def record_commit(_root: Path, commit: object) -> int:
        observed.append(commit)
        return 0

    monkeypatch.setattr("coador.kb.changed_files_since", record_commit)

    status = kb.status()
    assert status.state is State.FRESH
    assert status.git_commit == "a" * 40
    assert observed == ["a" * 40]


def test_reading_without_a_scan_raises(kb: KnowledgeBase) -> None:
    assert kb.load() is None
    with pytest.raises(FileNotFoundError):
        kb.require_profile()


def test_layer_and_section_lookup(kb: KnowledgeBase) -> None:
    kb.refresh()

    rows = kb.list_layers()
    assert len(rows) == 9
    assert rows[0]["id"] == "01_overview"
    assert int(rows[0]["detected"]) <= int(rows[0]["sections"])

    layer = kb.get_layer("03_architecture")
    assert layer is not None and layer.sections

    section = kb.get_section("03_architecture", "di_framework")
    assert section is not None and section.detected
    assert kb.get_section("03_architecture", "missing") is None


def test_inventory_pages_reconstruct_the_stored_order(kb: KnowledgeBase) -> None:
    kb.refresh()
    section = kb.get_section("08_ui_testing", "test_tag_inventory")
    assert section is not None

    cursor = None
    values: list[str] = []
    while True:
        page = kb.get_section_page("08_ui_testing", "test_tag_inventory", cursor=cursor, limit=1)
        assert page is not None and page.total == len(section.items)
        values.extend(page.section.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert values == section.items
    assert len(values) == len(set(values))


@pytest.mark.parametrize("cursor", ["", "-1", "01", "one", "999"])
def test_inventory_pages_reject_invalid_cursors(kb: KnowledgeBase, cursor: str) -> None:
    kb.refresh()
    with pytest.raises(ValueError, match=r"[Cc]ursor"):
        kb.get_section_page("08_ui_testing", "test_tag_inventory", cursor=cursor, limit=1)


def test_custom_kb_directory_keeps_the_repository_clean(repo_copy: Path, tmp_path: Path) -> None:
    external = tmp_path / "kb-elsewhere"
    kb = KnowledgeBase.for_repo(repo_copy, external)
    kb.refresh()

    assert (external / "profile.json").exists()
    assert not (repo_copy / ".coador").exists()


def test_corrupt_profile_is_reported_as_damaged_and_rebuilt(kb: KnowledgeBase) -> None:
    kb.refresh()
    kb.profile_path.write_text("not json", encoding="utf-8")
    assert kb.status().state is State.DAMAGED
    with pytest.raises(FileNotFoundError, match="damaged"):
        kb.load()
    assert kb.refresh().state is State.FRESH


def _snapshot(kb: KnowledgeBase) -> dict[str, bytes]:
    files = [kb.manifest_path, kb.profile_path, *sorted(kb.layers_dir.glob("*.md"))]
    return {path.name: path.read_bytes() for path in files}


@pytest.mark.parametrize("version", [1, 999, None])
def test_incompatible_profile_is_rejected_and_rebuilt_even_with_fresh_manifest(
    kb: KnowledgeBase, version: int | None
) -> None:
    kb.refresh()
    data = json.loads(kb.profile_path.read_text())
    data["schema_version"] = version
    kb.profile_path.write_text(json.dumps(data))
    assert kb.status().state is State.SCHEMA_MISMATCH
    with pytest.raises(FileNotFoundError, match="Incompatible profile schema"):
        kb.require_profile()
    assert kb.refresh().state is State.FRESH
    assert kb.require_profile().schema_version == SCHEMA_VERSION


def test_manifest_mismatch_blocks_profile_reads(kb: KnowledgeBase) -> None:
    kb.refresh()
    manifest = json.loads(kb.manifest_path.read_text())
    manifest["schema_version"] = 1
    kb.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError, match="Incompatible"):
        kb.get_layer("01_overview")


def test_cache_cannot_cite_newly_escaping_symlink(kb: KnowledgeBase, tmp_path: Path) -> None:
    kb.refresh()
    profile = kb.require_profile()
    evidence = next(
        ev
        for _, section in profile.iter_sections()
        for ev in section.evidence
        if ev.entry_type == "file"
    )
    target = kb.repo_root / evidence.path
    outside = tmp_path / "outside"
    outside.write_text("external canary")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(FileNotFoundError, match="Unsafe cached"):
        kb.require_profile()
