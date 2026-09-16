"""Turn a Gradle model into knowledge-base sections.

These sections replace the heuristic answers for the questions Gradle can
answer exactly: which modules exist, how they depend on each other, which
variants are configured and how instrumentation tests are run. Each one is
marked ``source: gradle`` so a reader can tell ground truth from a guess.
"""

from __future__ import annotations

from pathlib import Path

from coador.gradle_probe import GradleModel, GradleProject
from coador.model import (
    Evidence,
    InventoryCompleteness,
    Provenance,
    ResultKind,
    Section,
    Source,
)


def build_sections(model: GradleModel, repo_root: Path) -> dict[tuple[str, str], Section]:
    """Return the sections Gradle can answer, keyed by ``(layer id, section id)``."""
    sections = {
        ("04_modules_map", "full_module_list"): _module_list(model),
        ("04_modules_map", "module_classification"): _module_classification(model),
        ("04_modules_map", "module_dependency_graph"): _dependency_graph(model),
        ("02_build_and_run", "build_types_flavors_dimensions"): _variants(model),
        ("01_overview", "brands_flavors_presence"): _brands(model),
        ("07_testing", "test_config_knobs"): _test_configuration(model, repo_root),
    }
    return {key: section for key, section in sections.items() if section is not None}


def _module_list(model: GradleModel) -> Section | None:
    modules = [project.path for project in model.projects if project.path != ":"]
    if not modules:
        return None

    evidence = {
        project.path: [_model_evidence(project.path, "project.path", project.path)]
        for project in model.projects
        if project.path != ":"
    }
    return Section(
        id="full_module_list",
        title="Full Module List",
        detected=True,
        summary=f"{len(modules)} modules configured by Gradle",
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=sorted(modules),
        item_evidence=evidence,
        evidence=[item for items in evidence.values() for item in items],
        inventory_completeness=InventoryCompleteness.COMPLETE,
    )


def _module_classification(model: GradleModel) -> Section | None:
    if not model.projects:
        return None

    groups: dict[str, list[str]] = {}
    for project in model.projects:
        if project.path == ":":
            continue
        groups.setdefault(project.kind, []).append(project.path)

    if not groups:
        return None

    summary = ", ".join(f"{kind}: {len(paths)}" for kind, paths in sorted(groups.items()))
    items = [f"{path} - {kind}" for kind, paths in sorted(groups.items()) for path in sorted(paths)]
    item_evidence: dict[str, list[Evidence]] = {}
    for project in model.projects:
        if project.path == ":":
            continue
        item = f"{project.path} - {project.kind}"
        item_evidence[item] = [
            _model_evidence(
                project.path,
                "android.applicationId" if project.android else "plugins",
                project.android.application_id
                if project.android and project.android.application_id
                else "not configured"
                if project.android
                else ", ".join(project.plugins),
            )
        ]
    return Section(
        id="module_classification",
        title="Module Classification",
        detected=True,
        summary=summary,
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=items,
        item_evidence=item_evidence,
        evidence=[item for values in item_evidence.values() for item in values],
        inventory_completeness=InventoryCompleteness.COMPLETE,
    )


def _dependency_graph(model: GradleModel) -> Section | None:
    edges = [
        f"{project.path} -> {dependency}"
        for project in model.projects
        for dependency in project.project_dependencies
        if dependency != project.path
    ]
    if not edges:
        return None

    item_evidence = {
        f"{project.path} -> {dependency}": [
            _model_evidence(project.path, "projectDependencies", dependency)
        ]
        for project in model.projects
        for dependency in project.project_dependencies
        if dependency != project.path
    }
    return Section(
        id="module_dependency_graph",
        title="Module Dependency Graph",
        detected=True,
        summary=f"{len(edges)} dependencies between {len(model.projects)} modules",
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=sorted(edges),
        item_evidence=item_evidence,
        evidence=[item for values in item_evidence.values() for item in values],
        inventory_completeness=(
            InventoryCompleteness.COMPLETE
            if all(project.dependency_collection_complete is True for project in model.projects)
            else InventoryCompleteness.UNKNOWN
        ),
        limitations=(
            []
            if all(project.dependency_collection_complete is True for project in model.projects)
            else ["Some Gradle configurations may not expose their project dependencies"]
        ),
    )


def _variants(model: GradleModel) -> Section | None:
    applications = _applications(model)
    parts: list[str] = []
    items: list[str] = []
    item_evidence: dict[str, list[Evidence]] = {}
    section_evidence: list[Evidence] = []
    for application in applications:
        assert application.android is not None
        android = application.android
        project_parts = []
        if android.build_types:
            project_parts.append(f"build types: {', '.join(android.build_types)}")
        if android.flavor_dimensions:
            project_parts.append(f"dimensions: {', '.join(android.flavor_dimensions)}")
        if android.product_flavors:
            names = [flavor.name for flavor in android.product_flavors]
            project_parts.append(f"{len(names)} flavours: {', '.join(names)}")
        if project_parts:
            parts.append(f"{application.path} ({'; '.join(project_parts)})")

        for name in android.build_types:
            item = f"{application.path} - build type: {name}"
            evidence = _model_evidence(application.path, "android.buildTypes", name)
            items.append(item)
            item_evidence[item] = [evidence]
            section_evidence.append(evidence)
        for flavor in android.product_flavors:
            item = f"{application.path} - flavour: {flavor.name}"
            if flavor.dimension:
                item += f" (dimension {flavor.dimension})"
            if flavor.application_id_suffix:
                item += f", applicationIdSuffix {flavor.application_id_suffix}"
            evidence = _model_evidence(application.path, "android.productFlavors", flavor.name)
            items.append(item)
            item_evidence[item] = [evidence]
            section_evidence.append(evidence)
        section_evidence.extend(
            _model_evidence(application.path, "android.flavorDimensions", name)
            for name in android.flavor_dimensions
        )
    if not parts:
        return None

    complete = _android_properties_complete(
        applications, {"buildTypes", "flavorDimensions", "productFlavors"}
    )
    return Section(
        id="build_types_flavors_dimensions",
        title="Build Types / Flavors / Dimensions",
        detected=True,
        summary="; ".join(parts),
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=items,
        item_evidence=item_evidence,
        evidence=section_evidence,
        inventory_completeness=(
            InventoryCompleteness.COMPLETE if complete else InventoryCompleteness.UNKNOWN
        ),
        limitations=(
            [] if complete else ["Unavailable Android DSL properties are not negative facts"]
        ),
    )


def _brands(model: GradleModel) -> Section | None:
    applications = _applications(model)
    items: list[str] = []
    item_evidence: dict[str, list[Evidence]] = {}
    summaries: list[str] = []
    for application in applications:
        assert application.android is not None
        android = application.android
        if not android.product_flavors:
            continue
        names = [flavor.name for flavor in android.product_flavors]
        summary = f"{application.path}: {len(names)} product flavours"
        if android.flavor_dimensions:
            summary += f" across dimensions {', '.join(android.flavor_dimensions)}"
        suffixes = sum(1 for flavor in android.product_flavors if flavor.application_id_suffix)
        if suffixes:
            summary += f"; {suffixes} with applicationId suffix"
        summaries.append(summary)
        for flavor in android.product_flavors:
            item = f"{application.path} - {flavor.name}"
            items.append(item)
            item_evidence[item] = [
                _model_evidence(application.path, "android.productFlavors", flavor.name)
            ]
    if not items:
        return None
    complete = _android_properties_complete(applications, {"productFlavors"})
    return Section(
        id="brands_flavors_presence",
        title="Brands / Flavors Presence",
        detected=True,
        summary="; ".join(summaries),
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=items,
        item_evidence=item_evidence,
        evidence=[item for values in item_evidence.values() for item in values],
        inventory_completeness=(
            InventoryCompleteness.COMPLETE if complete else InventoryCompleteness.UNKNOWN
        ),
        limitations=(
            [] if complete else ["Unavailable Android DSL properties are not negative facts"]
        ),
    )


def _test_configuration(model: GradleModel, repo_root: Path) -> Section | None:
    applications = _applications(model)
    items: list[str] = []
    item_evidence: dict[str, list[Evidence]] = {}
    for project in applications:
        assert project.android is not None
        values = [
            (
                "android.testInstrumentationRunner",
                "testInstrumentationRunner",
                project.android.test_instrumentation_runner,
            ),
            (
                "android.testOptions.execution",
                "testOptions.execution",
                project.android.test_execution,
            ),
            (
                "android.testOptions.animationsDisabled",
                "testOptions.animationsDisabled",
                project.android.animations_disabled,
            ),
        ]
        for property_name, label, value in values:
            if value is None:
                continue
            item = f"{project.path} - {label} = {value}"
            model_evidence = _model_evidence(project.path, property_name, str(value))
            items.append(item)
            item_evidence[item] = [model_evidence]
    if not items:
        return None
    evidence_items = [item for values in item_evidence.values() for item in values]
    complete = _android_properties_complete(
        applications, {"testInstrumentationRunner", "testOptions"}
    )
    return Section(
        id="test_config_knobs",
        title="Test Config Knobs",
        detected=True,
        summary="Observed Gradle test configuration: " + "; ".join(items),
        kind=ResultKind.INVENTORY,
        source=Source.GRADLE,
        items=items,
        item_evidence=item_evidence,
        evidence=evidence_items,
        inventory_completeness=(
            InventoryCompleteness.COMPLETE if complete else InventoryCompleteness.UNKNOWN
        ),
        limitations=(
            [] if complete else ["Unavailable Android DSL properties are not negative facts"]
        ),
    )


def _applications(model: GradleModel) -> list[GradleProject]:
    return [project for project in model.android_projects if project.kind == "application"]


def _android_properties_complete(projects: list[GradleProject], properties: set[str]) -> bool:
    return bool(projects) and all(
        project.android is not None
        and project.android.availability_reported
        and not properties.intersection(project.android.unavailable_properties)
        for project in projects
    )


def _model_evidence(project: str, property: str, value: str) -> Evidence:
    return Evidence(
        provenance=Provenance.GRADLE_MODEL,
        project=project,
        property=property,
        snippet=value,
    )
