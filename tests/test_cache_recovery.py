from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import coador.kb as kb_module
import coador.scanner as scanner_module
from coador.kb import KnowledgeBase, State


def _manifest(kb: KnowledgeBase) -> dict[str, object]:
    return json.loads(kb.manifest_path.read_text(encoding="utf-8"))


def test_force_detects_content_changed_with_preserved_metadata(kb: KnowledgeBase) -> None:
    large = kb.repo_root / "Large.kt"
    large.write_bytes(b"a" * (70 * 1024) + b"LEFT")
    kb.refresh()
    before = _manifest(kb)["fingerprint_content"]
    stat = large.stat()

    large.write_bytes(b"a" * (70 * 1024) + b"RITE")
    os.utime(large, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert kb.status().state is State.FRESH  # documented metadata fast-path limitation
    assert kb.status(verify_content=True).state is State.STALE
    result = kb.refresh(force=True)
    assert result.state is State.FRESH
    assert result.refresh_action == "scanned"
    assert _manifest(kb)["fingerprint_content"] != before


def test_unchanged_refresh_skips_content_reads_and_detectors(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    monkeypatch.setattr(
        kb_module,
        "content_fingerprint",
        lambda *args, **kwargs: pytest.fail("quick path read source content"),
    )
    monkeypatch.setattr(
        kb_module,
        "scan_with_metadata",
        lambda *args, **kwargs: pytest.fail("quick path ran detectors"),
    )
    assert kb.refresh().refresh_action == "no_op"


def test_metadata_only_change_updates_manifest_without_scanning(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    before = _manifest(kb)
    source = kb.repo_root / "settings.gradle.kts"
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    monkeypatch.setattr(
        kb_module,
        "scan_with_metadata",
        lambda *args, **kwargs: pytest.fail("metadata-only refresh ran detectors"),
    )

    result = kb.refresh()
    after = _manifest(kb)
    assert result.refresh_action == "metadata_updated"
    assert after["scanned_at"] == before["scanned_at"]
    assert after["fingerprint_quick"] != before["fingerprint_quick"]
    assert after["fingerprint_content"] == before["fingerprint_content"]


def test_missing_layer_is_repaired_from_profile_without_scanning(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    missing = kb.layers_dir / "04_modules_map.md"
    missing.unlink()
    assert kb.status().state is State.DAMAGED

    def unexpected_scan(*args: object, **kwargs: object) -> object:
        raise AssertionError("layer repair must not run detectors")

    monkeypatch.setattr(kb_module, "scan_with_metadata", unexpected_scan)
    result = kb.refresh()
    assert result.state is State.FRESH
    assert result.refresh_action == "artifacts_repaired"
    assert missing.exists()


def test_missing_profile_requires_and_receives_a_full_rebuild(kb: KnowledgeBase) -> None:
    kb.refresh()
    kb.profile_path.unlink()
    assert kb.status().state is State.DAMAGED
    result = kb.refresh()
    assert result.refresh_action == "scanned"
    assert kb.require_profile().project_name == "mini-android"


def test_generated_body_repair_preserves_manual_header(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    layer = kb.layers_dir / "03_architecture.md"
    layer.write_text(
        "# Team-owned header\n\n" + layer.read_text(encoding="utf-8"), encoding="utf-8"
    )
    layer.write_text(
        layer.read_text(encoding="utf-8").replace("## Scan Results", "## Damaged Results"),
        encoding="utf-8",
    )
    assert kb.status().state is State.DAMAGED

    monkeypatch.setattr(
        kb_module,
        "scan_with_metadata",
        lambda *args, **kwargs: pytest.fail("generated-body repair ran detectors"),
    )
    result = kb.refresh()
    content = layer.read_text(encoding="utf-8")
    assert result.refresh_action == "artifacts_repaired"
    assert content.startswith("# Team-owned header\n")
    assert "## Scan Results" in content


def test_manual_header_is_outside_integrity_and_explicit_refresh_takes_effect(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    layer = kb.layers_dir / "03_architecture.md"
    layer.write_text("# Custom header\n\n" + layer.read_text(encoding="utf-8"), encoding="utf-8")
    assert kb.status().state is State.FRESH

    monkeypatch.setattr(
        kb_module,
        "scan_with_metadata",
        lambda *args, **kwargs: pytest.fail("header refresh ran detectors"),
    )
    result = kb.refresh(refresh_header=True)
    assert result.refresh_action == "headers_refreshed"
    assert layer.read_text(encoding="utf-8").startswith("# 03 Architecture\n")


def test_evidence_limit_is_a_cache_key(kb: KnowledgeBase) -> None:
    first = kb.refresh(evidence_limit=1)
    second = kb.refresh(evidence_limit=2)
    assert first.refresh_action == second.refresh_action == "scanned"
    assert _manifest(kb)["scan_options"] == {
        "evidence_limit": 2,
        "requested_mode": "heuristic",
        "gradle_timeout": None,
        "gradle_offline": None,
    }


def test_tool_contract_change_invalidates_and_rebuilds(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    monkeypatch.setattr(kb_module, "__version__", "99.0.test")
    assert kb.status().state is State.SCHEMA_MISMATCH
    result = kb.refresh()
    assert result.state is State.FRESH
    assert result.refresh_action == "scanned"
    assert _manifest(kb)["tool_version"] == "99.0.test"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_schema_version", 999),
        ("output_security_version", 999),
        ("generation_contract_version", 999),
    ],
)
def test_versioned_cache_contract_changes_require_rebuild(
    kb: KnowledgeBase, field: str, value: int
) -> None:
    kb.refresh()
    manifest = _manifest(kb)
    manifest[field] = value
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert kb.status().state is State.SCHEMA_MISMATCH
    result = kb.refresh()
    assert result.state is State.FRESH
    assert result.refresh_action == "scanned"


def test_corrupt_manifest_is_damaged_and_rebuilt(kb: KnowledgeBase) -> None:
    kb.refresh()
    kb.manifest_path.write_text("not json", encoding="utf-8")
    assert kb.status().state is State.DAMAGED
    assert kb.refresh().refresh_action == "scanned"


def test_incomplete_committed_layer_set_requires_rebuild(kb: KnowledgeBase) -> None:
    kb.refresh()
    manifest = _manifest(kb)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    layers = artifacts["layers"]
    assert isinstance(layers, dict)
    layers.pop("09_ci_cd.md")
    kb.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert kb.status().state is State.DAMAGED
    assert kb.refresh().refresh_action == "artifacts_repaired"


def test_custom_kb_inside_repository_is_stable_and_not_scanned(repo_copy: Path) -> None:
    custom = repo_copy / "generated" / "team-kb"
    kb = KnowledgeBase.for_repo(repo_copy, custom)
    first = kb.refresh()
    before = _manifest(kb)["fingerprint_quick"]
    second = kb.refresh()

    assert first.refresh_action == "scanned"
    assert second.refresh_action == "no_op"
    assert _manifest(kb)["fingerprint_quick"] == before
    profile = kb.require_profile()
    assert all(
        not evidence.path.startswith("generated/team-kb")
        for _, section in profile.iter_sections()
        for evidence in section.evidence
    )


def test_repository_root_cannot_be_used_as_the_kb_directory(repo_copy: Path) -> None:
    with pytest.raises(ValueError, match="cannot contain"):
        KnowledgeBase.for_repo(repo_copy, repo_copy)
    with pytest.raises(ValueError, match="cannot contain"):
        KnowledgeBase.for_repo(repo_copy, repo_copy.parent)


def test_mixed_generation_is_rejected_until_normal_refresh(kb: KnowledgeBase) -> None:
    kb.refresh()
    data = json.loads(kb.profile_path.read_text(encoding="utf-8"))
    data["project_name"] = "different-generation"
    kb.profile_path.write_text(json.dumps(data), encoding="utf-8")

    assert kb.status().state is State.DAMAGED
    with pytest.raises(FileNotFoundError, match="damaged"):
        kb.require_profile()
    assert kb.refresh().state is State.FRESH
    assert kb.require_profile().project_name == "mini-android"


def test_reader_rejects_partially_published_generation(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    (kb.repo_root / "settings.gradle.kts").write_text(
        'rootProject.name = "changed"\n', encoding="utf-8"
    )
    real_replace = kb_module._replace_file
    observed = False

    def observe(source: Path, target: Path) -> None:
        nonlocal observed
        real_replace(source, target)
        if target == kb.profile_path:
            observed = True
            with pytest.raises(FileNotFoundError, match="damaged"):
                kb.require_profile()

    monkeypatch.setattr(kb_module, "_replace_file", observe)
    assert kb.refresh().state is State.FRESH
    assert observed


def test_interrupted_publication_is_repaired_by_next_refresh(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb.refresh()
    (kb.repo_root / "settings.gradle.kts").write_text(
        'rootProject.name = "changed"\n', encoding="utf-8"
    )
    real_replace = kb_module._replace_file

    with monkeypatch.context() as scoped:

        def interrupt(source: Path, target: Path) -> None:
            if target.parent == kb.layers_dir:
                raise OSError("simulated interruption")
            real_replace(source, target)

        scoped.setattr(kb_module, "_replace_file", interrupt)
        with pytest.raises(OSError, match="simulated interruption"):
            kb.refresh()

    assert kb.status().state is State.DAMAGED
    assert kb.refresh().state is State.FRESH
    assert kb.require_profile().project_name == "changed"


def test_two_knowledge_base_instances_serialize_refresh(
    repo_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_kb = KnowledgeBase.for_repo(repo_copy)
    second_kb = KnowledgeBase.for_repo(repo_copy)
    real_scan = kb_module.scan_with_metadata
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def delayed_scan(*args: object, **kwargs: object) -> object:
        nonlocal calls
        with calls_lock:
            calls += 1
        entered.set()
        assert release.wait(timeout=5)
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(kb_module, "scan_with_metadata", delayed_scan)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_kb.refresh)
        assert entered.wait(timeout=5)
        second = pool.submit(second_kb.refresh)
        release.set()
        results = [first.result(timeout=10), second.result(timeout=10)]

    assert calls == 1
    assert {result.refresh_action for result in results} == {"scanned", "no_op"}
    assert first_kb.status().state is State.FRESH
    assert first_kb.lock_path.read_bytes() == b"\n"


def test_gradle_mode_and_fallback_are_recorded(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scanner_module,
        "_gradle_overrides",
        lambda *args, **kwargs: ({}, True),
    )
    status = kb.refresh(use_gradle=True, gradle_timeout=17, gradle_offline=True)
    assert status.scan_mode == "gradle"
    assert status.requested_scan_mode == "gradle"
    assert status.gradle_fallback is False
    assert _manifest(kb)["scan_options"] == {
        "evidence_limit": 25,
        "requested_mode": "gradle",
        "gradle_timeout": 17,
        "gradle_offline": True,
    }

    monkeypatch.setattr(
        scanner_module,
        "_gradle_overrides",
        lambda *args, **kwargs: ({}, False),
    )
    fallback = kb.refresh(use_gradle=True, gradle_timeout=18)
    assert fallback.scan_mode == "heuristic"
    assert fallback.requested_scan_mode == "gradle"
    assert fallback.gradle_fallback is True
    assert fallback.authority_change == "gradle_to_heuristic"


def test_heuristic_refresh_reports_gradle_authority_downgrade(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scanner_module,
        "_gradle_overrides",
        lambda *args, **kwargs: ({}, True),
    )
    assert kb.refresh(use_gradle=True).scan_mode == "gradle"
    result = kb.refresh(use_gradle=False)
    assert result.scan_mode == "heuristic"
    assert result.authority_change == "gradle_to_heuristic"
