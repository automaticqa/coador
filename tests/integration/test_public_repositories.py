"""Opt-in checks against real public Android projects.

These clone and, for the Gradle pass, configure a real build, so they are not
part of the normal suite. Run them with:

    COADOR_INTEGRATION=1 pytest -m slow

``nowinandroid`` is the interesting case: its flavours come from
``build-logic`` (``NiaFlavor``) and its modules apply convention plugins, so the
heuristic pass cannot see the variants and must say so rather than invent them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from coador.kb import KnowledgeBase
from coador.model import Profile, Source
from coador.scanner import scan

NOW_IN_ANDROID = "https://github.com/android/nowinandroid.git"
NOW_IN_ANDROID_REF = "12f80da6518e161ed16a06a68e71fb8a873576d6"
ARCHITECTURE_SAMPLES = "https://github.com/android/architecture-samples.git"
ARCHITECTURE_SAMPLES_REF = "ee66e1526b84c026615df032c705842b7d2a521f"
TESTING_SAMPLES = "https://github.com/android/testing-samples.git"
TESTING_SAMPLES_REF = "8c9df3a534ef99e44d481d96c00a5fc1970f7c70"


@dataclass(frozen=True)
class PublicRepository:
    name: str
    url: str
    revision: str


PUBLIC_REPOSITORIES = (
    PublicRepository("nowinandroid", NOW_IN_ANDROID, NOW_IN_ANDROID_REF),
    PublicRepository("architecture-samples", ARCHITECTURE_SAMPLES, ARCHITECTURE_SAMPLES_REF),
    PublicRepository("testing-samples", TESTING_SAMPLES, TESTING_SAMPLES_REF),
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("COADOR_INTEGRATION") != "1",
        reason="set COADOR_INTEGRATION=1 to run integration tests",
    ),
]


@pytest.fixture(scope="module")
def nowinandroid(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _checkout(
        PublicRepository("nowinandroid", NOW_IN_ANDROID, NOW_IN_ANDROID_REF), tmp_path_factory
    )


def _checkout(case: PublicRepository, tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")

    target = tmp_path_factory.mktemp(case.name) / "repo"
    subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(target), "fetch", "--depth", "1", case.url, case.revision],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"],
        check=True,
        capture_output=True,
    )
    assert (
        subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == case.revision
    )
    return target


@pytest.fixture(scope="module", params=PUBLIC_REPOSITORIES, ids=lambda case: case.name)
def public_profile(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[PublicRepository, Profile, float, int]:
    case: PublicRepository = request.param
    target = _checkout(case, tmp_path_factory)
    started = time.perf_counter()
    profile = scan(target, evidence_limit=25)
    elapsed = time.perf_counter() - started
    output_size = len(json.dumps(profile.to_dict(), ensure_ascii=False).encode())
    return case, profile, elapsed, output_size


def test_heuristic_scan_describes_the_project(nowinandroid: Path) -> None:
    profile = scan(nowinandroid)

    identity = profile.find_section("01_overview", "repository_identity")
    assert identity is not None and identity.detected

    di = profile.find_section("03_architecture", "di_framework")
    assert di is not None and di.detected
    assert "Hilt" in di.summary

    for _, section in profile.iter_sections():
        assert section.source is Source.HEURISTIC


def test_heuristics_do_not_invent_variants_defined_in_build_logic(nowinandroid: Path) -> None:
    """Flavours come from a convention plugin, so text matching must not claim names."""
    section = scan(nowinandroid).find_section("02_build_and_run", "build_types_flavors_dimensions")
    assert section is not None
    assert "demo" not in section.summary
    assert "prod" not in section.summary


def test_gradle_pass_recovers_the_variant_model(nowinandroid: Path) -> None:
    if shutil.which("java") is None:
        pytest.skip("a JDK is required for the Gradle pass")

    kb = KnowledgeBase.for_repo(nowinandroid)
    kb.refresh(use_gradle=True, gradle_timeout=1800)
    profile = kb.require_profile()

    variants = profile.find_section("02_build_and_run", "build_types_flavors_dimensions")
    assert variants is not None
    assert variants.source is Source.GRADLE
    assert "demo" in variants.summary and "prod" in variants.summary

    modules = profile.find_section("04_modules_map", "full_module_list")
    assert modules is not None
    assert modules.source is Source.GRADLE
    assert ":app" in modules.items
    assert len(modules.items) > 10


def test_pinned_public_repositories_answer_the_qa_questions(
    public_profile: tuple[PublicRepository, Profile, float, int], record_property
) -> None:
    case, profile, elapsed, output_size = public_profile
    record_property(f"{case.name}_scan_seconds", round(elapsed, 3))
    record_property(f"{case.name}_profile_bytes", output_size)

    question_sections = (
        ("07_testing", "instrumentation_runner"),
        ("07_testing", "test_tasks"),
        ("07_testing", "test_dependency_substitution"),
        ("07_testing", "test_entry_points"),
        ("08_ui_testing", "test_tag_inventory"),
        ("08_ui_testing", "deep_link_inventory"),
        ("08_ui_testing", "exported_components"),
        ("09_ci_cd", "artifacts_and_reports"),
    )
    for layer_id, section_id in question_sections:
        section = profile.find_section(layer_id, section_id)
        assert section is not None and section.error is None
        assert section.evidence or section.limitations
        if not section.is_signal:
            assert section.inventory_completeness is not None
            assert all(section.item_evidence[item] for item in section.items)

    expectations = {
        "nowinandroid": ("NiaTestRunner", "testTag: "),
        "architecture-samples": ("CustomTestRunner", "activity "),
        "testing-samples": ("Android Test Orchestrator", "view id: "),
    }
    summary_fragment, item_prefix = expectations[case.name]
    runner = profile.find_section("07_testing", "instrumentation_runner")
    assert runner is not None and summary_fragment in runner.summary
    assert any(
        item.startswith(item_prefix)
        for section_id in ("test_tag_inventory", "exported_components")
        for section in [profile.find_section("08_ui_testing", section_id)]
        if section is not None
        for item in section.items
    )
