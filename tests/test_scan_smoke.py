from __future__ import annotations

from pathlib import Path

from coador.model import Profile, Provenance
from coador.registry import DETECTORS, LAYERS
from coador.scanner import read_project_name, scan


def test_profile_covers_every_registered_detector(fixture_profile: Profile) -> None:
    assert [layer.id for layer in fixture_profile.layers] == [spec.id for spec in LAYERS]
    assert len(fixture_profile.iter_sections()) == len(DETECTORS)


def test_project_name_comes_from_the_settings_script(
    fixture_repo: Path, fixture_profile: Profile
) -> None:
    assert fixture_profile.project_name == "mini-android"
    assert read_project_name(fixture_repo) == "mini-android"


def test_project_name_falls_back_to_the_directory_name(tmp_path: Path) -> None:
    repo = tmp_path / "some-app"
    repo.mkdir()
    assert read_project_name(repo) == "some-app"


def test_relative_repository_root_is_supported() -> None:
    assert read_project_name(Path("tests/fixtures/mini_android")) == "mini-android"


def test_known_stacks_are_detected(fixture_profile: Profile) -> None:
    expectations = {
        ("01_overview", "repository_identity"): "mini-android",
        ("03_architecture", "di_framework"): "Hilt",
        ("03_architecture", "networking_stack"): "Retrofit",
        ("03_architecture", "persistence"): "Room",
        ("03_architecture", "navigation"): "Navigation",
        ("08_ui_testing", "kaspresso_framework"): "Kaspresso",
    }
    for (layer_id, section_id), expected in expectations.items():
        section = fixture_profile.find_section(layer_id, section_id)
        assert section is not None, f"{layer_id}/{section_id} missing"
        assert section.detected, f"{layer_id}/{section_id} not detected"
        assert expected in section.summary, section.summary
        assert section.evidence, f"{layer_id}/{section_id} has no evidence"


def test_evidence_uses_repository_relative_paths(
    fixture_profile: Profile, fixture_repo: Path
) -> None:
    for _, section in fixture_profile.iter_sections():
        for evidence in section.evidence:
            assert not evidence.path.startswith("/"), evidence.path
            assert not evidence.path.startswith(".."), evidence.path
            assert "\\" not in evidence.path
            source = fixture_repo / evidence.path
            assert source.exists()
            evidence.validate()
            if evidence.provenance is Provenance.SOURCE_LINES:
                assert evidence.line_start is not None and evidence.line_end is not None
                assert (
                    1
                    <= evidence.line_start
                    <= evidence.line_end
                    <= len(source.read_text().splitlines())
                )
            else:
                assert evidence.line_start is None and evidence.line_end is None


def test_evidence_limit_caps_entries_but_keeps_the_total(fixture_repo: Path) -> None:
    full = scan(fixture_repo)
    capped = scan(fixture_repo, evidence_limit=2)

    for _, section in capped.iter_sections():
        assert len(section.evidence) <= 2

    richest = max(full.iter_sections(), key=lambda pair: len(pair[1].evidence))
    layer_id, section = richest
    assert len(section.evidence) > 2, "fixture no longer exercises the evidence cap"

    capped_section = capped.find_section(layer_id.id, section.id)
    assert capped_section is not None
    assert capped_section.evidence_total == len(section.evidence)
    assert capped_section.truncated


def test_a_failing_detector_becomes_a_negative_section(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    profile = scan(empty)
    assert len(profile.iter_sections()) == len(DETECTORS)
    assert all(not section.detected for _, section in profile.iter_sections())


def test_progress_is_reported_for_every_detector(fixture_repo: Path) -> None:
    seen: list[tuple[int, int, str]] = []
    scan(fixture_repo, on_progress=lambda done, total, label: seen.append((done, total, label)))

    assert len(seen) == len(DETECTORS)
    assert seen[0][0] == 1
    assert seen[-1][0] == seen[-1][1] == len(DETECTORS)
