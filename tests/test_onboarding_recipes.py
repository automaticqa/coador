from pathlib import Path

from coador.registry import detector_spec

PUBLIC_REVISIONS = (
    "12f80da6518e161ed16a06a68e71fb8a873576d6",
    "ee66e1526b84c026615df032c705842b7d2a521f",
    "8c9df3a534ef99e44d481d96c00a5fc1970f7c70",
)

RECIPE_SECTIONS = (
    ("07_testing", "test_tasks"),
    ("09_ci_cd", "emulator_device_provisioning"),
    ("09_ci_cd", "artifacts_and_reports"),
    ("08_ui_testing", "exported_components"),
    ("08_ui_testing", "deep_link_inventory"),
    ("08_ui_testing", "test_tag_inventory"),
    ("07_testing", "instrumentation_runner"),
    ("07_testing", "test_dependency_substitution"),
    ("07_testing", "test_entry_points"),
)


def test_recipes_use_pinned_public_revisions_and_external_output() -> None:
    guide = Path("docs/onboarding-recipes.md").read_text(encoding="utf-8")

    for revision in PUBLIC_REVISIONS:
        assert f"checkout {revision}" in guide
        assert revision in guide

    assert guide.count("coador scan public/") == 3
    assert guide.count("--kb-dir /tmp/coador-recipes/") >= 3
    assert "runner/AndroidTestOrchestratorSample" in guide


def test_recipe_sections_are_registered_and_documented() -> None:
    guide = Path("docs/onboarding-recipes.md").read_text(encoding="utf-8")

    for layer_id, section_id in RECIPE_SECTIONS:
        assert detector_spec(layer_id, section_id) is not None
        assert f"{layer_id} {section_id}" in guide


def test_recipes_preserve_evidence_boundaries() -> None:
    guide = Path("docs/onboarding-recipes.md").read_text(encoding="utf-8")
    normalized_guide = " ".join(guide.split()).casefold()

    expected_boundaries = (
        "observed commands",
        "suggested commands",
        "not a complete list of executable Gradle tasks",
        "Missing heuristic evidence is not proof of absence",
        "manifests are not merged",
        "not exhaustive secret discovery",
        "does not query live CI",
        "must not be presented with invented line numbers",
    )
    for boundary in expected_boundaries:
        assert boundary.casefold() in normalized_guide


def test_readme_links_to_onboarding_recipes() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "[evidence-first onboarding recipes](docs/onboarding-recipes.md)" in readme
