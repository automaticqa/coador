from __future__ import annotations

from pathlib import Path

import pytest

from coador.model import (
    Evidence,
    InventoryCompleteness,
    Layer,
    Profile,
    Provenance,
    ResultKind,
    Section,
)
from coador.paths import UnsafePathError
from coador.registry import LAYERS, detectors_for
from coador.render.markdown import (
    GENERATED_BEGIN,
    GENERATED_END,
    extract_generated,
    render_generated,
    render_header,
    render_layer,
    write_layers,
)


def _layer() -> Layer:
    return Layer(
        id="03_architecture",
        title="Architecture",
        sections=[
            Section(
                id="di_framework",
                title="DI Framework",
                detected=True,
                summary="Hilt",
                evidence=[
                    Evidence.from_source("app/build.gradle.kts", "\n\n\nhilt", 4),
                ],
            ),
            Section(
                id="navigation",
                title="Navigation",
                detected=False,
                summary="No navigation signals",
            ),
        ],
    )


def test_header_lists_every_detector_of_the_layer() -> None:
    for spec in LAYERS:
        header = render_header(spec)
        assert header.startswith(f"# {spec.heading}")
        for detector in detectors_for(spec.id):
            assert detector.title in header, (spec.id, detector.title)
        if spec.note:
            assert spec.note in header


def test_rendered_layer_has_exactly_one_generated_block() -> None:
    text = render_layer(_layer())
    assert text.count(GENERATED_BEGIN) == 1
    assert text.count(GENERATED_END) == 1
    assert text.index(GENERATED_BEGIN) < text.index(GENERATED_END)
    assert text.rstrip().endswith(GENERATED_END)


def test_extract_generated_returns_only_the_generated_body() -> None:
    layer = _layer()
    text = render_layer(layer).replace("# 03 Architecture", "# Manual header")

    assert extract_generated(text) == render_generated(layer)
    assert "Manual header" not in (extract_generated(text) or "")


@pytest.mark.parametrize(
    "content",
    [
        "no markers",
        f"{GENERATED_BEGIN}\nbody",
        f"body\n{GENERATED_END}",
        f"{GENERATED_END}\nbody\n{GENERATED_BEGIN}",
        f"{GENERATED_BEGIN}\none\n{GENERATED_BEGIN}\ntwo\n{GENERATED_END}",
        f"{GENERATED_BEGIN}\nbody\n{GENERATED_END}\n{GENERATED_END}",
        f"{GENERATED_BEGIN}\nbody\n{GENERATED_END}\ntrailing",
    ],
)
def test_extract_generated_rejects_invalid_marker_pairs(content: str) -> None:
    assert extract_generated(content) is None


def test_extract_generated_accepts_an_empty_ordered_pair() -> None:
    assert extract_generated(f"{GENERATED_BEGIN}{GENERATED_END}") == ""


def test_sections_render_detected_state_and_evidence() -> None:
    text = render_layer(_layer())
    assert "### DI Framework" in text
    assert "**Detected:** Hilt" in text
    assert "- `app/build.gradle.kts:4` - hilt" in text
    assert "**Not found:** No navigation signals" in text


def test_truncated_evidence_is_announced() -> None:
    layer = _layer()
    layer.sections[0].evidence_total = 40
    assert "39 more of 40 matches not shown" in render_layer(layer)


def test_inventory_sections_render_items() -> None:
    layer = Layer(
        id="03_architecture",
        title="Architecture",
        sections=[
            Section(
                id="di_framework",
                title="DI Framework",
                detected=True,
                summary="2 entries",
                kind=ResultKind.INVENTORY,
                items=["alpha", "beta"],
                inventory_completeness=InventoryCompleteness.COMPLETE,
            )
        ],
    )
    text = render_layer(layer)
    assert "**All 2:**" in text
    assert "- alpha" in text and "- beta" in text


def test_all_provenance_shapes_and_inventory_support_evidence_render() -> None:
    layer = Layer(
        id="03_architecture",
        title="Architecture",
        sections=[
            Section(
                id="di_framework",
                title="DI",
                detected=True,
                summary="found",
                kind=ResultKind.INVENTORY,
                items=["entry"],
                evidence=[
                    Evidence(
                        path="app",
                        provenance=Provenance.FILE,
                        entry_type="directory",
                        snippet="sources",
                    ),
                    Evidence(
                        provenance=Provenance.GRADLE_MODEL,
                        project=":app",
                        property="android.buildTypes",
                        snippet="debug",
                    ),
                ],
            )
        ],
    )
    text = render_layer(layer)
    assert "app (directory)" in text
    assert "Gradle project :app, property android.buildTypes" in text
    assert "sources" in text and "debug" in text


def test_generated_fields_are_escaped_and_errors_are_not_not_found() -> None:
    section = _layer().sections[0]
    section.title = "### injected"
    section.summary = "<!-- GENERATED:BEGIN --> `token=CANARY`"
    section.error = "# failed <!-- GENERATED:BEGIN -->"
    text = render_layer(Layer(id="03_architecture", title="Architecture", sections=[section]))
    assert text.count(GENERATED_BEGIN) == 1
    assert "CANARY" not in text
    assert "### \\### injected" in text
    assert "**Error:**" in text
    assert "**Not found:**" not in text


def test_handwritten_header_survives_a_rescan() -> None:
    first = render_layer(_layer())
    edited = first.replace(
        "## Contents", "## Team notes\n\nOwned by the platform team.\n\n## Contents"
    )

    second = render_layer(_layer(), existing=edited)
    assert "Owned by the platform team." in second
    assert second.count(GENERATED_BEGIN) == 1


def test_handwritten_header_is_preserved_without_escaping() -> None:
    existing = "# Manual `header`\n\n> Keep this exactly.\n\n" + GENERATED_BEGIN + "\nold\n"
    text = render_layer(_layer(), existing=existing)
    assert text.startswith("# Manual `header`\n\n> Keep this exactly.\n\n")


def test_symlinked_output_directory_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(UnsafePathError):
        write_layers(Profile(project_name="x", layers=[_layer()]), linked)


def test_refresh_header_restores_the_template(tmp_path: Path) -> None:
    profile = Profile(project_name="x", layers=[_layer()])
    write_layers(profile, tmp_path)
    path = tmp_path / "03_architecture.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("# 03 Architecture", "# Custom"), encoding="utf-8"
    )

    write_layers(profile, tmp_path)
    assert "# Custom" in path.read_text(encoding="utf-8")

    write_layers(profile, tmp_path, refresh_header=True)
    assert "# 03 Architecture" in path.read_text(encoding="utf-8")


def test_staging_directory_preserves_header_from_existing_directory(tmp_path: Path) -> None:
    profile = Profile(project_name="x", layers=[_layer()])
    existing_dir = tmp_path / "existing"
    staging_dir = tmp_path / "staging"
    write_layers(profile, existing_dir)
    existing_path = existing_dir / "03_architecture.md"
    existing_path.write_text(
        existing_path.read_text(encoding="utf-8").replace("# 03 Architecture", "# Custom"),
        encoding="utf-8",
    )

    write_layers(profile, staging_dir, existing_dir=existing_dir)

    staged = (staging_dir / "03_architecture.md").read_text(encoding="utf-8")
    assert staged.startswith("# Custom\n")
    assert extract_generated(staged) == render_generated(_layer())


def test_staging_refresh_header_ignores_existing_directory(tmp_path: Path) -> None:
    profile = Profile(project_name="x", layers=[_layer()])
    existing_dir = tmp_path / "existing"
    staging_dir = tmp_path / "staging"
    write_layers(profile, existing_dir)
    existing_path = existing_dir / "03_architecture.md"
    existing_path.write_text(
        existing_path.read_text(encoding="utf-8").replace("# 03 Architecture", "# Custom"),
        encoding="utf-8",
    )

    write_layers(profile, staging_dir, refresh_header=True, existing_dir=existing_dir)

    staged = (staging_dir / "03_architecture.md").read_text(encoding="utf-8")
    assert staged.startswith("# 03 Architecture\n")


def test_rendering_is_byte_identical_between_runs(tmp_path: Path) -> None:
    profile = Profile(project_name="x", layers=[_layer()])
    write_layers(profile, tmp_path)
    first = (tmp_path / "03_architecture.md").read_bytes()

    write_layers(profile, tmp_path)
    assert (tmp_path / "03_architecture.md").read_bytes() == first


def test_generated_block_has_no_timestamp_or_absolute_path() -> None:
    text = render_layer(_layer())
    assert "Generated:" not in text
    assert "Source:" not in text
    assert "/home/" not in text
