"""Markdown projection of a profile.

Each layer file is a hand-editable header followed by a generated block between
GENERATED:BEGIN and GENERATED:END markers. Only the generated block is rewritten
by a scan, so notes added above it survive. Nothing inside the file depends on
the scan time or on absolute paths, which keeps re-scans byte-identical.
"""

from __future__ import annotations

from pathlib import Path

from coador.model import (
    Evidence,
    InventoryCompleteness,
    Layer,
    Profile,
    Provenance,
    Section,
    Source,
)
from coador.paths import UnsafePathError, checked_path
from coador.registry import LayerSpec, detectors_for, layer_spec
from coador.render.json_io import atomic_write_text

GENERATED_BEGIN = "<!-- GENERATED:BEGIN -->"
GENERATED_END = "<!-- GENERATED:END -->"


def _generated_text(value: object) -> str:
    """Render model-derived text as Markdown text, never Markdown structure."""
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in ("\\", "`", "*", "_", "[", "]"):
        text = text.replace(character, f"\\{character}")
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        newline = line[len(content) :]
        prefix_length = len(content) - len(content.lstrip())
        prefix, remainder = content[:prefix_length], content[prefix_length:]
        if remainder.startswith(("#", ">", "+", "-")) or (
            len(remainder) > 1 and remainder[0].isdigit() and remainder[1] in ".)"
        ):
            remainder = "\\" + remainder
        lines.append(prefix + remainder + newline)
    return "".join(lines)


def _code_text(value: object) -> str:
    """Encode the only delimiter that can escape the surrounding code span."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("`", "&#96;")
    )


def _safe_section(section: Section) -> Section:
    return Section.from_dict(section.to_dict())


def _safe_layer(layer: Layer) -> Layer:
    return Layer.from_dict(layer.to_dict())


def _safe_profile(profile: Profile) -> Profile:
    return Profile.from_dict(profile.to_dict())


def render_header(spec: LayerSpec) -> str:
    """Render the default hand-editable part: title, table of contents, optional note."""
    lines = [f"# {spec.heading}", "", "## Contents", ""]
    for index, detector in enumerate(detectors_for(spec.id), start=1):
        lines.append(f"{index}. {detector.title}")
    if spec.note:
        lines.extend(["", f"> Note: {spec.note}"])
    return "\n".join(lines) + "\n"


def extract_header(content: str) -> str:
    """Return the hand-written part of an existing layer file."""
    if GENERATED_BEGIN in content:
        return content[: content.index(GENERATED_BEGIN)].rstrip() + "\n"
    return content.rstrip() + "\n"


def extract_generated(content: str) -> str | None:
    """Return the generated body when ``content`` has exactly one ordered marker pair."""
    if content.count(GENERATED_BEGIN) != 1 or content.count(GENERATED_END) != 1:
        return None
    begin = content.index(GENERATED_BEGIN) + len(GENERATED_BEGIN)
    end = content.index(GENERATED_END)
    if begin > end:
        return None
    if content[end + len(GENERATED_END) :] not in {"", "\n"}:
        return None
    body = content[begin:end]
    return body.removeprefix("\n")


def render_evidence(section: Section) -> list[str]:
    section = _safe_section(section)
    lines: list[str] = []
    if section.evidence:
        lines.append("")
        lines.append("**Evidence:**")
        for item in section.evidence:
            lines.append(
                f"- `{_code_text(_evidence_location(item))}` - {_generated_text(item.snippet)}"
            )
        if section.truncated:
            shown, total = len(section.evidence), section.evidence_total
            lines.append(f"- _... {total - shown} more of {total} matches not shown_")
    return lines


def _evidence_location(item: Evidence) -> str:
    if item.provenance is Provenance.GRADLE_MODEL:
        return f"Gradle project {item.project}, property {item.property}"
    if item.provenance is Provenance.FILE:
        return f"{item.path} ({item.entry_type})"
    if item.line_start == item.line_end:
        return f"{item.path}:{item.line_start}"
    return f"{item.path}:{item.line_start}-{item.line_end}"


SOURCE_LABELS = {Source.GRADLE: "from Gradle"}


def render_section(section: Section) -> str:
    section = _safe_section(section)
    label = "Error" if section.error else ("Detected" if section.detected else "Not found")
    origin = SOURCE_LABELS.get(section.source)
    if origin:
        label = f"{label} ({origin})"
    detail = section.error if section.error else section.summary
    lines = [f"### {_generated_text(section.title)}", "", f"**{label}:** {_generated_text(detail)}"]

    if section.is_signal:
        lines.extend(render_evidence(section))
    elif section.items:
        lines.append("")
        if section.inventory_completeness is InventoryCompleteness.COMPLETE:
            lines.append(f"**All {section.evidence_total}:**")
        else:
            status = section.inventory_completeness or InventoryCompleteness.UNKNOWN
            lines.append(f"**Collected {section.evidence_total} ({status.value} inventory):**")
        lines.extend(f"- {_generated_text(item)}" for item in section.items)
        lines.extend(render_evidence(section))

    if section.collection_stop_reason:
        lines.extend(
            ["", f"**Collection stopped:** {_generated_text(section.collection_stop_reason)}"]
        )
    if section.limitations:
        lines.extend(["", "**Limitations:**"])
        lines.extend(f"- {_generated_text(item)}" for item in section.limitations)

    lines.append("")
    return "\n".join(lines)


def render_generated(layer: Layer) -> str:
    layer = _safe_layer(layer)
    lines = ["## Scan Results", ""]
    for section in layer.sections:
        lines.append(render_section(section))
    return "\n".join(lines)


def render_layer(layer: Layer, *, existing: str | None = None) -> str:
    """Render one layer file, preserving the hand-written header when present."""
    layer = _safe_layer(layer)
    spec = layer_spec(layer.id)
    if spec is None:
        raise KeyError(f"Unknown layer: {layer.id}")

    header = extract_header(existing) if existing else render_header(spec)
    return f"{header}\n{GENERATED_BEGIN}\n{render_generated(layer)}{GENERATED_END}\n"


def write_layers(
    profile: Profile,
    output_dir: Path,
    *,
    refresh_header: bool = False,
    existing_dir: Path | None = None,
) -> list[Path]:
    """Write every layer of ``profile`` into ``output_dir`` and return the paths."""
    profile = _safe_profile(profile)
    if output_dir.is_symlink():
        raise UnsafePathError("Linked output directories are not supported")
    header_dir = output_dir if existing_dir is None else existing_dir
    if header_dir.is_symlink():
        raise UnsafePathError("Linked existing directories are not supported")
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise UnsafePathError("Linked output directories are not supported")
    written: list[Path] = []

    for layer in profile.layers:
        spec = layer_spec(layer.id)
        if spec is None:
            continue
        path = checked_path(output_dir, spec.filename)
        existing = None
        existing_path = checked_path(header_dir, spec.filename)
        if existing_path.exists() and not refresh_header:
            try:
                existing = existing_path.read_text(encoding="utf-8")
            except OSError:
                existing = None
        atomic_write_text(path, render_layer(layer, existing=existing))
        written.append(path)

    return written
