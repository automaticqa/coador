from __future__ import annotations

import pytest

from coador.model import (
    SCHEMA_VERSION,
    Evidence,
    InventoryCompleteness,
    Layer,
    Profile,
    ResultKind,
    Section,
    Source,
)


def _signal() -> Section:
    return Section(
        id="di_framework",
        title="DI Framework",
        detected=True,
        summary="Hilt",
        evidence=[Evidence.from_source("app/build.gradle.kts", "\n\n\nhilt", 4)],
    )


def _inventory() -> Section:
    return Section(
        id="deep_links",
        title="Deep Links",
        detected=True,
        summary="2 deep links",
        kind=ResultKind.INVENTORY,
        items=["https://example.com/a", "https://example.com/b"],
    )


def test_profile_round_trips_through_json() -> None:
    profile = Profile(
        project_name="mini-android",
        layers=[
            Layer(id="03_architecture", title="Architecture", sections=[_signal(), _inventory()])
        ],
    )
    restored = Profile.from_dict(profile.to_dict())
    assert restored == profile
    assert restored.to_dict()["schema_version"] == SCHEMA_VERSION


def test_signal_section_carries_evidence_and_inventory_carries_items() -> None:
    signal, inventory = _signal(), _inventory()
    assert signal.is_signal and "evidence" in signal.to_dict()
    assert not inventory.is_signal and "items" in inventory.to_dict()
    assert "evidence" not in inventory.to_dict()


def test_inventory_items_round_trip_with_all_supporting_evidence() -> None:
    first = Evidence.from_source("app/src/main/AndroidManifest.xml", "<data />", 1)
    second = Evidence.from_source("feature/src/main/AndroidManifest.xml", "<data />", 1)
    section = Section(
        id="deep_links",
        title="Deep Links",
        detected=True,
        summary="one link",
        kind=ResultKind.INVENTORY,
        items=["https://example.com", "https://example.com"],
        item_evidence={"https://example.com": [first, second, first]},
        inventory_completeness=InventoryCompleteness.INCOMPLETE,
        collection_limit=5000,
        collection_stop_reason="collection limit reached",
        limitations=["Merged manifests were not evaluated"],
    )

    restored = Section.from_dict(section.to_dict())

    assert restored.items == ["https://example.com"]
    assert restored.item_evidence["https://example.com"] == [first, second]
    assert restored.inventory_completeness is InventoryCompleteness.INCOMPLETE
    assert restored.collection_limit == 5000
    assert restored.collection_stop_reason == "collection limit reached"
    assert restored.limitations == ["Merged manifests were not evaluated"]


def test_inventory_completeness_and_stop_reason_must_agree() -> None:
    with pytest.raises(ValueError, match="stop reason"):
        Section(
            id="items",
            title="Items",
            detected=True,
            summary="bounded",
            kind=ResultKind.INVENTORY,
            inventory_completeness=InventoryCompleteness.INCOMPLETE,
        )
    with pytest.raises(ValueError, match="Only an incomplete"):
        Section(
            id="items",
            title="Items",
            detected=True,
            summary="complete",
            kind=ResultKind.INVENTORY,
            inventory_completeness=InventoryCompleteness.COMPLETE,
            collection_stop_reason="unexpected",
        )


def test_evidence_total_defaults_to_the_number_of_entries() -> None:
    assert _signal().evidence_total == 1
    assert _inventory().evidence_total == 2


def test_truncated_reports_capped_evidence() -> None:
    section = _signal()
    assert not section.truncated

    section.evidence_total = 40
    assert section.truncated
    assert not _inventory().truncated


def test_lookup_helpers() -> None:
    layer = Layer(id="03_architecture", title="Architecture", sections=[_signal()])
    profile = Profile(project_name="x", layers=[layer])

    assert profile.layer("03_architecture") is layer
    assert profile.layer("missing") is None
    assert profile.find_section("03_architecture", "di_framework") is not None
    assert profile.find_section("03_architecture", "missing") is None
    assert len(profile.iter_sections()) == 1


def test_defaults_are_heuristic_signals() -> None:
    section = _signal()
    assert section.kind is ResultKind.SIGNAL
    assert section.source is Source.HEURISTIC
