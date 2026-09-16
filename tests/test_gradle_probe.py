from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from coador.gradle_probe import GradleProbeError, parse_model, probe
from coador.gradle_sections import build_sections
from coador.model import InventoryCompleteness, Provenance, ResultKind, Source

OUTPUT = (Path(__file__).parent / "data" / "gradle_model_output.txt").read_text(encoding="utf-8")


def _wrapper_path(root: Path) -> Path:
    return root / ("gradlew.bat" if os.name == "nt" else "gradlew")


def _model():
    return parse_model(OUTPUT, repo_root=Path("/repo"))


def test_the_main_build_wins_over_included_builds() -> None:
    """An init script runs for buildSrc too; root identity selects the requested build."""
    model = _model()
    assert model.root_project == "mini-android"
    assert len(model.projects) == 4


def test_requested_root_wins_even_when_an_included_build_has_more_projects() -> None:
    def block(root: str, project_count: int) -> str:
        projects = [
            {"path": f":p{index}", "dir": f"{root}/p{index}", "plugins": []}
            for index in range(project_count)
        ]
        return (
            "COADOR_MODEL_BEGIN\n"
            + json.dumps(
                {
                    "rootProject": Path(root).name,
                    "rootDir": root,
                    "gradleVersion": "8.0",
                    "projects": projects,
                }
            )
            + "\nCOADOR_MODEL_END\n"
        )

    output = block("/included", 5) + block("/wanted", 1)

    assert parse_model(output, repo_root=Path("/wanted")).root_project == "wanted"
    with pytest.raises(GradleProbeError, match="multiple models"):
        parse_model(output)


def test_android_projects_are_classified() -> None:
    model = _model()
    kinds = {project.path: project.kind for project in model.projects}
    assert kinds[":app"] == "application"
    assert kinds[":core:network"] == "library"
    assert kinds[":build-logic"] == "jvm"


def test_variant_model_is_read() -> None:
    android = _model().project(":app").android
    assert android is not None
    assert android.build_types == ("debug", "release")
    assert android.flavor_dimensions == ("brand",)
    assert [flavor.name for flavor in android.product_flavors] == ["demo", "prod"]
    assert android.product_flavors[0].application_id_suffix == ".demo"
    assert android.test_instrumentation_runner == "com.example.mini.HiltTestRunner"
    assert android.test_execution == "androidx_test_orchestrator"
    assert android.animations_disabled is True


def test_output_without_a_model_is_an_error() -> None:
    with pytest.raises(GradleProbeError):
        parse_model("BUILD SUCCESSFUL in 2s\n")


def test_broken_json_is_an_error() -> None:
    with pytest.raises(GradleProbeError):
        parse_model("COADOR_MODEL_BEGIN\n{not json}\nCOADOR_MODEL_END\n")


def test_malformed_model_shape_is_a_controlled_error() -> None:
    with pytest.raises(GradleProbeError) as raised:
        parse_model('COADOR_MODEL_BEGIN\n{"projects":"CANARY_MODEL_SHAPE"}\nCOADOR_MODEL_END\n')

    assert str(raised.value) == "Gradle model has invalid structure"
    assert "CANARY_MODEL_SHAPE" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_probe_without_a_wrapper_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(GradleProbeError, match="No Gradle wrapper"):
        probe(tmp_path)


def test_probe_failure_does_not_expose_gradle_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _wrapper_path(tmp_path).touch()
    completed = subprocess.CompletedProcess(
        args=["gradlew"],
        returncode=17,
        stdout="CANARY_STDOUT",
        stderr="CANARY_STDERR",
    )
    with (
        patch("coador.gradle_probe.subprocess.run", return_value=completed),
        pytest.raises(GradleProbeError) as raised,
    ):
        probe(tmp_path)

    assert str(raised.value) == "Gradle probe produced no model (exit 17)"
    assert "CANARY" not in str(raised.value)
    assert "CANARY" not in caplog.text


def test_probe_timeout_does_not_expose_process_output(tmp_path: Path) -> None:
    _wrapper_path(tmp_path).touch()
    timeout = subprocess.TimeoutExpired(
        cmd=["gradlew"], timeout=12, output="CANARY_STDOUT", stderr="CANARY_STDERR"
    )
    with (
        patch("coador.gradle_probe.subprocess.run", side_effect=timeout),
        pytest.raises(GradleProbeError) as raised,
    ):
        probe(tmp_path, timeout=12)

    assert str(raised.value) == "Gradle probe timed out after 12s"
    assert "CANARY" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_probe_start_failure_does_not_expose_exception_text(tmp_path: Path) -> None:
    _wrapper_path(tmp_path).touch()
    with (
        patch(
            "coador.gradle_probe.subprocess.run",
            side_effect=OSError("CANARY_OS_ERROR"),
        ),
        pytest.raises(GradleProbeError) as raised,
    ):
        probe(tmp_path)

    assert str(raised.value) == "Gradle probe could not start"
    assert "CANARY" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_linked_wrapper_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "wrapper-target"
    target.touch()
    wrapper = _wrapper_path(tmp_path)
    try:
        wrapper.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(GradleProbeError, match="wrapper is unsafe") as raised:
        probe(tmp_path)

    assert raised.value.__cause__ is None


def test_sections_are_marked_as_coming_from_gradle(tmp_path: Path) -> None:
    sections = build_sections(_model(), tmp_path)
    assert sections
    for section in sections.values():
        assert section.source is Source.GRADLE
        assert section.kind is ResultKind.INVENTORY
        assert section.items
        assert section.inventory_completeness is not None
        assert all(section.item_evidence[item] for item in section.items)


def test_gradle_overrides_have_model_provenance(tmp_path: Path) -> None:
    sections = build_sections(_model(), tmp_path)
    expected_properties = {
        ("04_modules_map", "full_module_list"): {"project.path"},
        ("04_modules_map", "module_classification"): {"android.applicationId", "plugins"},
        ("04_modules_map", "module_dependency_graph"): {"projectDependencies"},
        ("02_build_and_run", "build_types_flavors_dimensions"): {
            "android.buildTypes",
            "android.flavorDimensions",
            "android.productFlavors",
        },
        ("01_overview", "brands_flavors_presence"): {"android.productFlavors"},
        ("07_testing", "test_config_knobs"): {
            "android.testInstrumentationRunner",
            "android.testOptions.execution",
            "android.testOptions.animationsDisabled",
        },
    }

    assert set(sections) == set(expected_properties)
    for key, properties in expected_properties.items():
        evidence = sections[key].evidence
        assert {item.property for item in evidence} == properties
        for item in evidence:
            assert item.provenance is Provenance.GRADLE_MODEL
            assert item.project
            assert item.snippet
            assert item.path == ""
            assert item.line_start is None
            assert item.line_end is None


def test_module_sections_describe_the_build(tmp_path: Path) -> None:
    sections = build_sections(_model(), tmp_path)

    modules = sections[("04_modules_map", "full_module_list")]
    assert modules.items == [":app", ":build-logic", ":core:network"]

    classification = sections[("04_modules_map", "module_classification")]
    assert ":app - application" in classification.items

    graph = sections[("04_modules_map", "module_dependency_graph")]
    assert ":app -> :core:network" in graph.items
    assert ":app -> :app" not in graph.items, "a module must not depend on itself"


def test_variant_and_brand_sections(tmp_path: Path) -> None:
    sections = build_sections(_model(), tmp_path)

    variants = sections[("02_build_and_run", "build_types_flavors_dimensions")]
    assert "build types: debug, release" in variants.summary
    assert ":app - flavour: demo (dimension brand), applicationIdSuffix .demo" in variants.items

    brands = sections[("01_overview", "brands_flavors_presence")]
    assert brands.items == [":app - demo", ":app - prod"]
    assert "2 product flavours" in brands.summary


def test_test_configuration_section(tmp_path: Path) -> None:
    section = build_sections(_model(), tmp_path)[("07_testing", "test_config_knobs")]
    assert "com.example.mini.HiltTestRunner" in section.summary
    assert "androidx_test_orchestrator" in section.summary
    assert ":app - testOptions.animationsDisabled = True" in section.items


def test_a_build_without_android_yields_no_variant_sections(tmp_path: Path) -> None:
    plain = (
        'COADOR_MODEL_BEGIN\n{"gradleVersion":"8.0","rootProject":"x",'
        '"projects":[{"path":":lib","dir":"/x/lib","plugins":[],"projectDependencies":[]}]}'
        "\nCOADOR_MODEL_END\n"
    )
    sections = build_sections(parse_model(plain), tmp_path)
    assert ("02_build_and_run", "build_types_flavors_dimensions") not in sections
    assert ("04_modules_map", "full_module_list") in sections


def test_multiple_application_modules_keep_project_specific_facts(tmp_path: Path) -> None:
    projects = []
    for path, flavor, runner in [
        (":app", "demo", "example.AppRunner"),
        (":admin", "internal", "example.AdminRunner"),
    ]:
        projects.append(
            {
                "path": path,
                "dir": f"/repo/{path[1:]}",
                "plugins": ["com.android.application"],
                "androidPluginKind": "application",
                "android": {
                    "buildTypes": ["debug"],
                    "flavorDimensions": ["brand"],
                    "productFlavors": [{"name": flavor, "dimension": "brand"}],
                    "testInstrumentationRunner": runner,
                    "testOptions": {"execution": "androidx_test_orchestrator"},
                    "unavailableProperties": [],
                },
                "projectDependencies": [],
                "projectDependenciesComplete": True,
            }
        )
    output = (
        "COADOR_MODEL_BEGIN\n"
        + json.dumps(
            {
                "rootProject": "multi",
                "rootDir": "/repo",
                "gradleVersion": "8.0",
                "projects": projects,
            }
        )
        + "\nCOADOR_MODEL_END\n"
    )

    sections = build_sections(parse_model(output), tmp_path)
    variants = sections[("02_build_and_run", "build_types_flavors_dimensions")]
    brands = sections[("01_overview", "brands_flavors_presence")]
    test_config = sections[("07_testing", "test_config_knobs")]

    assert {item.split(" - ", 1)[0] for item in variants.items} == {":app", ":admin"}
    assert brands.items == [":app - demo", ":admin - internal"]
    assert any(
        item == ":app - testInstrumentationRunner = example.AppRunner" for item in test_config.items
    )
    assert any(
        item == ":admin - testInstrumentationRunner = example.AdminRunner"
        for item in test_config.items
    )
    assert test_config.inventory_completeness is InventoryCompleteness.COMPLETE


def test_unavailable_gradle_properties_are_unknown_not_negative(tmp_path: Path) -> None:
    data = {
        "rootProject": "partial",
        "gradleVersion": "8.0",
        "projects": [
            {
                "path": ":app",
                "dir": "/repo/app",
                "plugins": ["com.android.application"],
                "androidPluginKind": "application",
                "android": {
                    "buildTypes": ["debug"],
                    "testOptions": {"execution": "androidx_test_orchestrator"},
                    "unavailableProperties": ["testInstrumentationRunner", "productFlavors"],
                },
                "projectDependencies": [],
                "projectDependenciesComplete": False,
            }
        ],
    }
    output = "COADOR_MODEL_BEGIN\n" + json.dumps(data) + "\nCOADOR_MODEL_END\n"

    sections = build_sections(parse_model(output), tmp_path)
    variants = sections[("02_build_and_run", "build_types_flavors_dimensions")]
    test_config = sections[("07_testing", "test_config_knobs")]

    assert variants.inventory_completeness is InventoryCompleteness.UNKNOWN
    assert test_config.inventory_completeness is InventoryCompleteness.UNKNOWN
    assert all("testInstrumentationRunner" not in item for item in test_config.items)
    assert test_config.limitations
