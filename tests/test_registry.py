from __future__ import annotations

from pathlib import Path

import pytest

from coador import detectors
from coador.registry import (
    DETECTORS,
    LAYERS,
    detector_catalog_markdown,
    detector_spec,
    detectors_for,
    layer_spec,
)

# The legacy per-layer factory functions must keep agreeing with the registry
# for the layers they cover; the test-runtime family is registry-only.
_FACTORIES = {
    "01_overview": detectors.get_overview_detectors,
    "02_build_and_run": detectors.get_build_detectors,
    "03_architecture": detectors.get_architecture_detectors,
    "04_modules_map": detectors.get_modules_detectors,
    "05_config_and_env": detectors.get_config_detectors,
    "06_dependencies": detectors.get_dependencies_detectors,
    "07_testing": detectors.get_testing_detectors,
    "08_ui_testing": detectors.get_ui_testing_detectors,
    "09_ci_cd": detectors.get_ci_cd_detectors,
}


def test_every_layer_has_detectors() -> None:
    assert len(LAYERS) == 9
    for spec in LAYERS:
        assert detectors_for(spec.id), spec.id


def test_detector_ids_are_unique_within_a_layer() -> None:
    seen: set[tuple[str, str]] = set()
    for spec in DETECTORS:
        key = (spec.layer, spec.id)
        assert key not in seen, key
        seen.add(key)


def test_detector_ids_look_like_identifiers() -> None:
    for spec in DETECTORS:
        assert spec.id.replace("_", "").isalnum(), spec.id
        assert spec.id.islower(), spec.id


def test_every_registered_layer_is_known() -> None:
    layer_ids = {spec.id for spec in LAYERS}
    for spec in DETECTORS:
        assert spec.layer in layer_ids, spec.layer
        assert layer_spec(spec.layer) is not None


def test_registry_matches_the_detector_factories(tmp_path: Path) -> None:
    for layer_id, factory in _FACTORIES.items():
        from_factory = [type(detector).__name__ for detector in factory(tmp_path)]
        from_registry = [spec.detector_class.__name__ for spec in detectors_for(layer_id)]
        assert from_registry[: len(from_factory)] == from_factory, layer_id


def test_titles_are_unique_within_a_layer() -> None:
    for layer in {spec.layer for spec in DETECTORS}:
        titles = [spec.title for spec in detectors_for(layer)]
        assert len(titles) == len(set(titles)), layer


def test_a_detector_class_may_serve_several_layers(tmp_path: Path) -> None:
    """Config injection is one implementation rendered in two layers."""
    build_spec = detector_spec("02_build_and_run", "config_injection_mechanisms")
    config_spec = detector_spec("05_config_and_env", "config_injection")
    assert build_spec is not None and config_spec is not None
    assert build_spec.detector_class is config_spec.detector_class
    assert build_spec.title != config_spec.title


def test_detector_lookup(tmp_path: Path) -> None:
    assert detector_spec("03_architecture", "di_framework") is not None
    assert detector_spec("03_architecture", "nope") is None
    assert detector_spec("nope", "di_framework") is None


def test_layer_filenames_and_headings() -> None:
    assert LAYERS[0].filename == "01_overview.md"
    assert LAYERS[0].heading == "01 Project Overview"


def test_every_detector_is_described_for_search_and_docs() -> None:
    for spec in DETECTORS:
        assert spec.description, spec.id
        assert spec.description[0].isupper(), spec.id
        assert spec.description.endswith("."), spec.id
        assert spec.keywords, spec.id
        # Identifier keywords keep their real spelling (rootProject, testTag);
        # the search tokenizer is what normalises them.
        assert all(keyword.strip() == keyword and keyword for keyword in spec.keywords), spec.id
        assert len(set(spec.keywords)) == len(spec.keywords), spec.id


def test_detector_catalogue_is_up_to_date() -> None:
    """docs/detectors.md is generated; regenerate it with `python -m coador.registry`."""
    catalogue = Path(__file__).resolve().parents[1] / "docs" / "detectors.md"
    if not catalogue.exists():
        pytest.skip("catalogue is not part of this checkout")
    assert catalogue.read_text(encoding="utf-8") == detector_catalog_markdown() + "\n"
