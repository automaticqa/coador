"""Runs the registered detectors over a repository and assembles a Profile."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coador.detectors.base import DetectionResult
from coador.detectors.base import Evidence as DetectorEvidence
from coador.fileindex import active_index, get_index
from coador.fileindex import invalidate as invalidate_index
from coador.gradle_probe import DEFAULT_TIMEOUT_SECONDS, GradleProbeError, probe
from coador.gradle_sections import build_sections
from coador.model import (
    Evidence,
    InventoryCompleteness,
    Layer,
    Profile,
    Provenance,
    ResultKind,
    Section,
)
from coador.paths import checked_path
from coador.redact import sanitize_snippet
from coador.registry import DETECTORS, LAYERS, DetectorSpec
from coador.textscan import read_file_content

logger = logging.getLogger(__name__)

# Evidence is a sample that lets a reader verify a claim, not an exhaustive list;
# the full number of matches is kept in ``Section.evidence_total``.
DEFAULT_EVIDENCE_LIMIT = 25

ProgressCallback = Callable[[int, int, str], None]

_ROOT_PROJECT_NAME_RE = re.compile(r"""rootProject\.name\s*=\s*["']([^"']+)["']""")


@dataclass(frozen=True)
class ScanOutcome:
    """A profile plus the authority actually obtained by an optional Gradle probe."""

    profile: Profile
    requested_mode: str
    effective_mode: str
    gradle_fallback: bool = False


def read_project_name(repo_root: Path) -> str:
    """Return ``rootProject.name`` from the settings script, or the directory name."""
    repo_root = repo_root.resolve()
    index = get_index(repo_root)
    for name in ("settings.gradle.kts", "settings.gradle"):
        settings = index.find(name)
        if settings is None:
            continue
        content = read_file_content(settings, root=repo_root)
        if content is None:
            continue
        match = _ROOT_PROJECT_NAME_RE.search(content)
        if match:
            return match.group(1)
    return repo_root.name


def _to_model_evidence(evidence: DetectorEvidence, repo_root: Path) -> Evidence:
    path = checked_path(repo_root, evidence.file_path, directory=True)
    if not path.exists():
        raise ValueError("Source entry unavailable")
    if evidence.provenance is Provenance.SOURCE_LINES:
        if evidence.exact is None or not get_index(repo_root).verifies(evidence.exact):
            raise ValueError("Unverified source range")
        if evidence.exact.path != path.relative_to(repo_root).as_posix():
            raise ValueError("Mismatched source reference")
        evidence.exact.validate()
        return evidence.exact
    result = Evidence(
        path=path.relative_to(repo_root).as_posix(),
        snippet=evidence.snippet,
        provenance=Provenance.FILE,
        entry_type="directory" if path.is_dir() else "file",
    )
    result.validate()
    return result


def _build_section(
    spec: DetectorSpec,
    result: DetectionResult,
    evidence_limit: int | None,
    repo_root: Path,
) -> Section:
    evidence: list[Evidence] = []
    accepted_items: list[str] = []
    accepted_item_evidence: dict[str, list[Evidence]] = {}
    converted_evidence: dict[DetectorEvidence, Evidence] = {}
    rejected_evidence: set[DetectorEvidence] = set()
    rejected = 0
    for item in result.evidence:
        try:
            model_evidence = _to_model_evidence(item, repo_root)
            converted_evidence[item] = model_evidence
            evidence.append(model_evidence)
            value = sanitize_snippet(item.snippet)
            accepted_items.append(value)
            accepted_item_evidence.setdefault(value, []).append(model_evidence)
        except (ValueError, OSError):
            rejected += 1
            rejected_evidence.add(item)
    total = len(evidence)

    # An inventory answers "list all of them", so the list is never truncated;
    # the evidence below it stays a sample.
    items: list[str] = []
    item_evidence: dict[str, list[Evidence]] = {}
    if spec.kind is ResultKind.INVENTORY:
        candidate_items = list(
            dict.fromkeys(
                sanitize_snippet(item)
                for item in (result.items if result.items is not None else accepted_items)
            )
        )
        detector_item_evidence = {
            sanitize_snippet(value): value_evidence
            for value, value_evidence in result.item_evidence.items()
        } or {sanitize_snippet(value): [] for value in (result.items or [])}
        for value in candidate_items:
            detector_evidence = detector_item_evidence.get(value)
            if detector_evidence:
                for item in detector_evidence:
                    if item in rejected_evidence:
                        continue
                    try:
                        converted_item = converted_evidence.get(item)
                        if converted_item is None:
                            converted_item = _to_model_evidence(item, repo_root)
                            converted_evidence[item] = converted_item
                        item_evidence.setdefault(value, []).append(converted_item)
                    except (ValueError, OSError):
                        rejected += 1
                        rejected_evidence.add(item)
            else:
                item_evidence[value] = accepted_item_evidence.get(value, [])
            if item_evidence.get(value):
                items.append(value)
        total = len(items)

    if evidence_limit is not None and len(evidence) > evidence_limit:
        evidence = evidence[:evidence_limit]

    return Section(
        id=spec.id,
        title=spec.title,
        detected=result.detected and (not rejected or bool(evidence) or bool(items)),
        summary=result.description,
        kind=spec.kind,
        evidence=evidence,
        items=items,
        item_evidence=item_evidence,
        inventory_completeness=(
            result.inventory_completeness or InventoryCompleteness.UNKNOWN
            if spec.kind is ResultKind.INVENTORY
            else None
        ),
        collection_limit=result.collection_limit,
        collection_stop_reason=result.collection_stop_reason,
        evidence_total=total,
        error=result.error
        or (f"Omitted {rejected} invalid evidence entries" if rejected else None),
        limitations=result.limitations,
    )


def run_detector(spec: DetectorSpec, repo_root: Path) -> DetectionResult:
    """Run one detector, converting a crash into a negative result."""
    try:
        token = active_index.set(get_index(repo_root))
        try:
            return spec.build(repo_root).detect()
        finally:
            active_index.reset(token)
    except Exception:  # a broken detector must not abort the whole scan
        logger.warning("%s/%s: detector failed", spec.layer, spec.id)
        return DetectionResult(
            detected=False, description="Detection unavailable", error="Detector failed"
        )


def scan(
    repo_root: Path,
    *,
    evidence_limit: int | None = None,
    on_progress: ProgressCallback | None = None,
    use_gradle: bool = False,
    gradle_timeout: int = DEFAULT_TIMEOUT_SECONDS,
    gradle_offline: bool = False,
    excluded_paths: tuple[Path, ...] = (),
) -> Profile:
    """Scan ``repo_root`` and return its profile.

    With ``use_gradle`` the build's own configuration is queried first, and the
    questions Gradle can answer exactly replace the heuristic answers.
    """
    return scan_with_metadata(
        repo_root,
        evidence_limit=evidence_limit,
        on_progress=on_progress,
        use_gradle=use_gradle,
        gradle_timeout=gradle_timeout,
        gradle_offline=gradle_offline,
        excluded_paths=excluded_paths,
    ).profile


def scan_with_metadata(
    repo_root: Path,
    *,
    evidence_limit: int | None = None,
    on_progress: ProgressCallback | None = None,
    use_gradle: bool = False,
    gradle_timeout: int = DEFAULT_TIMEOUT_SECONDS,
    gradle_offline: bool = False,
    excluded_paths: tuple[Path, ...] = (),
) -> ScanOutcome:
    """Scan and retain whether requested Gradle authority was actually available."""
    repo_root = repo_root.resolve()
    invalidate_index(repo_root)
    index = get_index(repo_root, excluded_paths=excluded_paths)
    token = active_index.set(index)
    try:
        overrides, gradle_available = (
            _gradle_overrides(repo_root, timeout=gradle_timeout, offline=gradle_offline)
            if use_gradle
            else ({}, False)
        )
        profile = _assemble_profile(
            repo_root,
            overrides,
            evidence_limit=evidence_limit,
            on_progress=on_progress,
        )
    finally:
        active_index.reset(token)

    return ScanOutcome(
        profile=Profile.from_dict(profile.to_dict()),
        requested_mode="gradle" if use_gradle else "heuristic",
        effective_mode="gradle" if gradle_available else "heuristic",
        gradle_fallback=use_gradle and not gradle_available,
    )


def _assemble_profile(
    repo_root: Path,
    overrides: dict[tuple[str, str], Section],
    *,
    evidence_limit: int | None,
    on_progress: ProgressCallback | None,
) -> Profile:
    profile = Profile(project_name=read_project_name(repo_root))
    total = len(DETECTORS)
    done = 0

    for layer_spec in LAYERS:
        layer = Layer(id=layer_spec.id, title=layer_spec.title)
        for spec in DETECTORS:
            if spec.layer != layer_spec.id:
                continue
            override = overrides.get((layer_spec.id, spec.id))
            if override is not None:
                layer.sections.append(override)
            else:
                result = run_detector(spec, repo_root)
                layer.sections.append(_build_section(spec, result, evidence_limit, repo_root))
            section = layer.sections[-1]
            done += 1
            logger.debug(
                "[%s] %s/%s: %s",
                "+" if section.detected else "-",
                layer.id,
                section.id,
                section.summary,
            )
            if on_progress is not None:
                on_progress(done, total, f"{layer.id}/{spec.id}")
        logger.info("%s: %d/%d detected", layer.id, layer.detected_count, len(layer.sections))
        profile.layers.append(layer)

    return profile


def _gradle_overrides(
    repo_root: Path, *, timeout: int, offline: bool
) -> tuple[dict[tuple[str, str], Section], bool]:
    """Query Gradle, or log why it could not be queried and fall back to heuristics."""
    try:
        model = probe(repo_root, timeout=timeout, offline=offline)
    except GradleProbeError as exc:
        logger.warning("Gradle model unavailable, using heuristics only: %s", exc)
        return {}, False

    logger.info(
        "Gradle %s reported %d projects (%d Android)",
        sanitize_snippet(model.gradle_version),
        len(model.projects),
        len(model.android_projects),
    )
    return build_sections(model, repo_root), True
