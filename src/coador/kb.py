"""The knowledge base stored inside a scanned repository.

Everything the CLI and the MCP server do goes through :class:`KnowledgeBase`:
it owns the layout of ``.coador/``, decides whether a scan is needed, and
reads the profile back.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from coador import __version__
from coador.fingerprint import collect_entries, content_fingerprint, quick_fingerprint
from coador.gitinfo import changed_files_since, normalize_git_object_id, read_git_info
from coador.gradle_probe import DEFAULT_TIMEOUT_SECONDS as GRADLE_TIMEOUT_SECONDS
from coador.locking import exclusive_file_lock
from coador.model import (
    SCHEMA_VERSION,
    Layer,
    Profile,
    Provenance,
    ResultKind,
    SchemaMismatchError,
    Section,
)
from coador.paths import checked_path, open_source, read_text
from coador.redact import sanitize_public, sanitize_snippet
from coador.registry import LAYERS
from coador.render.json_io import read_json, read_profile, write_json, write_profile
from coador.render.markdown import extract_generated, write_layers
from coador.scanner import DEFAULT_EVIDENCE_LIMIT, ProgressCallback, scan_with_metadata
from coador.search import Hit, LexicalRetriever

logger = logging.getLogger(__name__)

KB_DIR_NAME = ".coador"
MANIFEST_NAME = "manifest.json"
PROFILE_NAME = "profile.json"
LAYERS_DIR_NAME = "layers"
LOCK_NAME = ".refresh.lock"

# Profile and manifest evolve independently. Increment these when a persisted
# output can no longer be trusted under the current cache or sanitization rules.
MANIFEST_SCHEMA_VERSION = 2
OUTPUT_SECURITY_VERSION = 1
GENERATION_CONTRACT_VERSION = 1
DEFAULT_INVENTORY_PAGE_SIZE = 100
MAX_INVENTORY_PAGE_SIZE = 200

# The sections that answer "what kind of project is this" in one screen.
HIGHLIGHTS: tuple[tuple[str, str, str], ...] = (
    ("01_overview", "repository_identity", "identity"),
    ("01_overview", "ui_technology_signals", "ui"),
    ("02_build_and_run", "build_types_flavors_dimensions", "variants"),
    ("03_architecture", "di_framework", "di"),
    ("03_architecture", "networking_stack", "networking"),
    ("03_architecture", "persistence", "persistence"),
    ("03_architecture", "navigation", "navigation"),
    ("04_modules_map", "full_module_list", "modules"),
    ("07_testing", "non_ui_test_frameworks", "unit_testing"),
    ("07_testing", "instrumentation_runner", "test_runner"),
    ("08_ui_testing", "kaspresso_framework", "ui_testing"),
    ("09_ci_cd", "ci_entrypoints", "ci"),
)


class State(StrEnum):
    """Whether the stored knowledge base can still be trusted."""

    MISSING = "missing"
    FRESH = "fresh"
    STALE = "stale"
    DAMAGED = "damaged"
    SCHEMA_MISMATCH = "schema_mismatch"


@dataclass(frozen=True)
class Status:
    """A snapshot of the knowledge base against the current working tree."""

    state: State
    files_count: int
    repo_path: str | None = None
    scanned_at: str | None = None
    tool_version: str | None = None
    schema_version: int | None = None
    git_commit: str | None = None
    git_dirty: bool | None = None
    git_root: str | None = None
    head_commit: str | None = None
    changed_files: int | None = None
    reason: str | None = None
    scan_mode: str | None = None
    requested_scan_mode: str | None = None
    gradle_fallback: bool | None = None
    evidence_limit: int | None = None
    refresh_action: str | None = None
    authority_change: str | None = None

    @property
    def needs_refresh(self) -> bool:
        return self.state is not State.FRESH

    def describe(self) -> str:
        """One-line, human-readable summary, including git context when available."""
        if self.state is State.MISSING:
            return "No knowledge base found; run `coador scan`"
        if self.state is State.SCHEMA_MISMATCH:
            if self.reason == "profile schema is incompatible":
                return "Incompatible profile schema; run `coador scan`"
            return "Incompatible knowledge-base cache contract; run `coador scan`"
        if self.state is State.DAMAGED:
            detail = f" ({self.reason})" if self.reason else ""
            return f"Knowledge base is incomplete or damaged{detail}; run `coador scan`"

        parts = [
            "Knowledge base is up to date"
            if self.state is State.FRESH
            else "Knowledge base is out of date; run `coador scan`",
            f"scanned {self.scanned_at}" if self.scanned_at else "",
            f"{self.files_count} files",
        ]
        if self.git_commit:
            git_part = f"built at {self.git_commit[:12]}"
            if self.head_commit and self.head_commit != self.git_commit:
                git_part += f", HEAD {self.head_commit[:12]}"
            if self.changed_files:
                git_part += f", {self.changed_files} files changed since"
            if self.git_root and self.repo_path and Path(self.git_root) != Path(self.repo_path):
                git_part += f" (work tree {self.git_root})"
            parts.append(git_part)
        if self.scan_mode:
            mode = f"scan mode {self.scan_mode}"
            if self.gradle_fallback:
                mode += " (Gradle unavailable; heuristic fallback)"
            parts.append(mode)
        if self.authority_change:
            parts.append(f"authority changed: {self.authority_change}")
        return ", ".join(part for part in parts if part)


@dataclass(frozen=True)
class SectionPage:
    """A section plus deterministic paging metadata for inventory items."""

    section: Section
    offset: int | None = None
    limit: int | None = None
    total: int | None = None
    next_cursor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.section.to_dict()
        if self.total is not None:
            data["pagination"] = {
                "offset": self.offset,
                "limit": self.limit,
                "returned": len(self.section.items),
                "total": self.total,
                "next_cursor": self.next_cursor,
            }
        return data


@dataclass(frozen=True)
class ScanOptions:
    evidence_limit: int | None
    requested_mode: str
    gradle_timeout: int | None = None
    gradle_offline: bool | None = None

    @classmethod
    def requested(
        cls,
        *,
        evidence_limit: int | None,
        use_gradle: bool,
        gradle_timeout: int,
        gradle_offline: bool,
    ) -> ScanOptions:
        return cls(
            evidence_limit=evidence_limit,
            requested_mode="gradle" if use_gradle else "heuristic",
            gradle_timeout=gradle_timeout if use_gradle else None,
            gradle_offline=gradle_offline if use_gradle else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_limit": self.evidence_limit,
            "requested_mode": self.requested_mode,
            "gradle_timeout": self.gradle_timeout,
            "gradle_offline": self.gradle_offline,
        }

    @classmethod
    def from_manifest(cls, value: object) -> ScanOptions | None:
        if not isinstance(value, dict):
            return None
        evidence_limit = value.get("evidence_limit")
        if evidence_limit is not None and (
            not isinstance(evidence_limit, int) or isinstance(evidence_limit, bool)
        ):
            return None
        requested_mode = value.get("requested_mode")
        if requested_mode not in {"heuristic", "gradle"}:
            return None
        timeout = value.get("gradle_timeout")
        offline = value.get("gradle_offline")
        if requested_mode == "gradle":
            if not isinstance(timeout, int) or isinstance(timeout, bool):
                return None
            if not isinstance(offline, bool):
                return None
        elif timeout is not None or offline is not None:
            return None
        return cls(evidence_limit, requested_mode, timeout, offline)


@dataclass
class CacheInspection:
    state: State
    manifest: dict[str, Any]
    profile: Profile | None = None
    profile_valid: bool = False
    layers_valid: bool = False
    reason: str | None = None

    @property
    def complete(self) -> bool:
        return self.state is State.FRESH and self.profile_valid and self.layers_valid


@dataclass
class KnowledgeBase:
    """Reads and refreshes the knowledge base of one repository."""

    repo_root: Path
    kb_dir: Path

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        # A selected output directory is a separate boundary, not a source reference.
        self.kb_dir = checked_path(
            self.kb_dir.parent.resolve(), self.kb_dir.absolute(), directory=True
        )
        if self.kb_dir == self.repo_root or self.kb_dir in self.repo_root.parents:
            raise ValueError("The knowledge-base directory cannot contain the repository root")

    @classmethod
    def for_repo(cls, repo_root: Path, kb_dir: Path | None = None) -> KnowledgeBase:
        return cls(repo_root=repo_root, kb_dir=kb_dir or repo_root / KB_DIR_NAME)

    @property
    def manifest_path(self) -> Path:
        return checked_path(self.kb_dir, self.kb_dir / MANIFEST_NAME)

    @property
    def profile_path(self) -> Path:
        return checked_path(self.kb_dir, self.kb_dir / PROFILE_NAME)

    @property
    def layers_dir(self) -> Path:
        return checked_path(self.kb_dir, self.kb_dir / LAYERS_DIR_NAME, directory=True)

    @property
    def lock_path(self) -> Path:
        return checked_path(self.kb_dir, self.kb_dir / LOCK_NAME)

    def _excluded_paths(self) -> tuple[Path, ...]:
        try:
            self.kb_dir.relative_to(self.repo_root)
        except ValueError:
            return ()
        return (self.kb_dir,)

    def status(self, *, verify_content: bool = False) -> Status:
        """Compare a coherent stored generation with the working tree."""
        inspection = self._inspect_cache()
        if not inspection.complete:
            return self._status_from(inspection, files_count=0)

        entries = collect_entries(self.repo_root, excluded_paths=self._excluded_paths())
        quick = quick_fingerprint(entries)
        state = State.FRESH
        reason = None
        if verify_content or quick != inspection.manifest.get("fingerprint_quick"):
            content = content_fingerprint(entries)
            if content != inspection.manifest.get("fingerprint_content"):
                state = State.STALE
                reason = "repository content changed"
        return self._status_from(
            inspection,
            state=state,
            reason=reason,
            files_count=len(entries),
        )

    def refresh(
        self,
        *,
        force: bool = False,
        evidence_limit: int | None = DEFAULT_EVIDENCE_LIMIT,
        refresh_header: bool = False,
        on_progress: ProgressCallback | None = None,
        use_gradle: bool = False,
        gradle_timeout: int = GRADLE_TIMEOUT_SECONDS,
        gradle_offline: bool = False,
    ) -> Status:
        """Repair or rebuild under one writer lock, publishing the manifest last."""
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        with exclusive_file_lock(self.lock_path):
            return self._refresh_locked(
                force=force,
                evidence_limit=evidence_limit,
                refresh_header=refresh_header,
                on_progress=on_progress,
                use_gradle=use_gradle,
                gradle_timeout=gradle_timeout,
                gradle_offline=gradle_offline,
            )

    def load(self) -> Profile | None:
        inspection = self._inspect_cache()
        if inspection.state is State.MISSING:
            return None
        if not inspection.complete or inspection.profile is None:
            raise FileNotFoundError(f"{self._status_from(inspection, files_count=0).describe()}")
        self._validate_source_references(inspection.profile)
        return inspection.profile

    def _inspect_cache(self) -> CacheInspection:
        if not self.manifest_path.exists():
            return CacheInspection(State.MISSING, {}, reason="manifest is missing")
        manifest = read_json(self.manifest_path)
        if not manifest:
            return CacheInspection(State.DAMAGED, {}, reason="manifest is unreadable")

        if (
            _as_int(manifest.get("manifest_schema_version")) != MANIFEST_SCHEMA_VERSION
            or _as_int(manifest.get("profile_schema_version")) != SCHEMA_VERSION
            or _as_int(manifest.get("schema_version")) != SCHEMA_VERSION
            or _as_int(manifest.get("output_security_version")) != OUTPUT_SECURITY_VERSION
            or _as_int(manifest.get("generation_contract_version")) != GENERATION_CONTRACT_VERSION
            or _as_str(manifest.get("tool_version")) != __version__
        ):
            return CacheInspection(
                State.SCHEMA_MISMATCH,
                manifest,
                reason="cache contract is incompatible",
            )
        try:
            normalize_git_object_id(manifest.get("git_commit"))
        except ValueError:
            return CacheInspection(State.DAMAGED, manifest, reason="Git commit is invalid")
        if ScanOptions.from_manifest(manifest.get("scan_options")) is None:
            return CacheInspection(State.DAMAGED, manifest, reason="scan options are invalid")
        if manifest.get("requested_scan_mode") not in {"heuristic", "gradle"}:
            return CacheInspection(State.DAMAGED, manifest, reason="requested scan mode is invalid")
        if manifest.get("effective_scan_mode") not in {"heuristic", "gradle"}:
            return CacheInspection(State.DAMAGED, manifest, reason="effective scan mode is invalid")
        if not isinstance(manifest.get("gradle_fallback"), bool):
            return CacheInspection(
                State.DAMAGED, manifest, reason="Gradle fallback state is invalid"
            )
        if manifest.get("header_policy") not in {"preserve", "refresh"}:
            return CacheInspection(State.DAMAGED, manifest, reason="header policy is invalid")

        try:
            profile = read_profile(self.profile_path)
        except SchemaMismatchError:
            return CacheInspection(
                State.SCHEMA_MISMATCH,
                manifest,
                reason="profile schema is incompatible",
            )
        if profile is None or not _profile_is_complete(profile):
            return CacheInspection(
                State.DAMAGED, manifest, reason="profile is incomplete or unreadable"
            )

        inspection = CacheInspection(
            State.DAMAGED,
            manifest,
            profile=profile,
            reason="profile does not match the committed generation",
        )
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            return inspection
        profile_digest = artifacts.get(PROFILE_NAME)
        if (
            not isinstance(profile_digest, str)
            or _file_digest(self.kb_dir, self.profile_path) != profile_digest
        ):
            return inspection
        inspection.profile_valid = True

        layer_digests = artifacts.get(LAYERS_DIR_NAME)
        expected_names = {spec.filename for spec in LAYERS}
        if not isinstance(layer_digests, dict) or set(layer_digests) != expected_names:
            inspection.reason = "required layer set is incomplete"
            return inspection
        for spec in LAYERS:
            expected = layer_digests.get(spec.filename)
            if not isinstance(expected, str):
                inspection.reason = f"layer {spec.filename} has no committed digest"
                return inspection
            path = checked_path(self.layers_dir, self.layers_dir / spec.filename)
            if _generated_digest(self.layers_dir, path) != expected:
                inspection.reason = f"layer {spec.filename} is missing or damaged"
                return inspection
        inspection.layers_valid = True

        expected_generation = _generation_digest(manifest)
        if manifest.get("generation_digest") != expected_generation:
            inspection.reason = "generation commit digest is invalid"
            return inspection
        inspection.state = State.FRESH
        inspection.reason = None
        return inspection

    def _refresh_locked(
        self,
        *,
        force: bool,
        evidence_limit: int | None,
        refresh_header: bool,
        on_progress: ProgressCallback | None,
        use_gradle: bool,
        gradle_timeout: int,
        gradle_offline: bool,
    ) -> Status:
        options = ScanOptions.requested(
            evidence_limit=evidence_limit,
            use_gradle=use_gradle,
            gradle_timeout=gradle_timeout,
            gradle_offline=gradle_offline,
        )
        inspection = self._inspect_cache()
        entries = collect_entries(self.repo_root, excluded_paths=self._excluded_paths())
        quick = quick_fingerprint(entries)
        stored_options = ScanOptions.from_manifest(inspection.manifest.get("scan_options"))
        options_match = stored_options == options
        source_same = False
        content: str | None = None

        can_compare_source = (
            inspection.profile_valid and inspection.state is not State.SCHEMA_MISMATCH
        )
        if not force and can_compare_source and options_match:
            if quick == inspection.manifest.get("fingerprint_quick"):
                source_same = True
            else:
                content = content_fingerprint(entries)
                source_same = content == inspection.manifest.get("fingerprint_content")

        retry_gradle = bool(
            use_gradle and inspection.manifest.get("gradle_fallback") and inspection.complete
        )
        if source_same and inspection.complete and not retry_gradle:
            if refresh_header and inspection.profile is not None:
                self._publish_layers(
                    inspection.profile,
                    inspection.manifest,
                    refresh_header=True,
                )
                return self._completed_status("headers_refreshed")
            if quick != inspection.manifest.get("fingerprint_quick"):
                assert content is not None
                manifest = self._updated_metadata_manifest(
                    inspection.manifest,
                    entries_count=len(entries),
                    quick=quick,
                    content=content,
                )
                write_json(self.manifest_path, manifest)
                logger.info("Only file timestamps changed (%d files)", len(entries))
                return self._completed_status("metadata_updated")
            logger.info("No changes detected (%d files)", len(entries))
            return self._completed_status("no_op")

        if (
            source_same
            and inspection.profile_valid
            and not inspection.layers_valid
            and inspection.profile is not None
            and not retry_gradle
        ):
            self._publish_layers(
                inspection.profile,
                inspection.manifest,
                refresh_header=refresh_header,
            )
            return self._completed_status("artifacts_repaired")

        if content is None:
            content = content_fingerprint(entries)
        logger.info("Scanning repository (%d files)", len(entries))
        outcome = scan_with_metadata(
            self.repo_root,
            evidence_limit=evidence_limit,
            on_progress=on_progress,
            use_gradle=use_gradle,
            gradle_timeout=gradle_timeout,
            gradle_offline=gradle_offline,
            excluded_paths=self._excluded_paths(),
        )

        final_entries = collect_entries(self.repo_root, excluded_paths=self._excluded_paths())
        final_content = content_fingerprint(final_entries)
        if final_content != content:
            raise RuntimeError("Repository content changed during scan; retry the refresh")
        final_quick = quick_fingerprint(final_entries)
        previous_mode = _as_str(inspection.manifest.get("effective_scan_mode"))
        authority_change = (
            f"{previous_mode}_to_{outcome.effective_mode}"
            if previous_mode and previous_mode != outcome.effective_mode
            else None
        )
        self._publish_generation(
            outcome.profile,
            entries_count=len(final_entries),
            quick=final_quick,
            content=final_content,
            options=options,
            requested_mode=outcome.requested_mode,
            effective_mode=outcome.effective_mode,
            gradle_fallback=outcome.gradle_fallback,
            refresh_header=refresh_header,
        )
        if authority_change:
            logger.warning("Scan authority changed: %s", authority_change)
        return self._completed_status("scanned", authority_change=authority_change)

    def _publish_generation(
        self,
        profile: Profile,
        *,
        entries_count: int,
        quick: str,
        content: str,
        options: ScanOptions,
        requested_mode: str,
        effective_mode: str,
        gradle_fallback: bool,
        refresh_header: bool,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=self.kb_dir, prefix=".staging-") as raw_stage:
            stage = Path(raw_stage)
            stage_profile = stage / PROFILE_NAME
            stage_layers = stage / LAYERS_DIR_NAME
            write_profile(stage_profile, profile)
            write_layers(
                profile,
                stage_layers,
                refresh_header=refresh_header,
                existing_dir=self.layers_dir,
            )
            artifacts = _artifact_digests(stage, stage_profile, stage_layers)
            manifest = self._manifest(
                entries_count=entries_count,
                quick=quick,
                content=content,
                options=options,
                requested_mode=requested_mode,
                effective_mode=effective_mode,
                gradle_fallback=gradle_fallback,
                refresh_header=refresh_header,
                artifacts=artifacts,
            )
            write_json(stage / MANIFEST_NAME, manifest)
            self._publish_stage(stage)

    def _publish_layers(
        self,
        profile: Profile,
        old_manifest: dict[str, Any],
        *,
        refresh_header: bool,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=self.kb_dir, prefix=".staging-") as raw_stage:
            stage = Path(raw_stage)
            stage_layers = stage / LAYERS_DIR_NAME
            write_layers(
                profile,
                stage_layers,
                refresh_header=refresh_header,
                existing_dir=self.layers_dir,
            )
            profile_digest = _file_digest(self.kb_dir, self.profile_path)
            layer_digests = {
                spec.filename: _generated_digest(stage_layers, stage_layers / spec.filename)
                for spec in LAYERS
            }
            if profile_digest is None or any(value is None for value in layer_digests.values()):
                raise RuntimeError("Could not stage a complete knowledge-base generation")
            artifacts: dict[str, object] = {
                PROFILE_NAME: profile_digest,
                LAYERS_DIR_NAME: {
                    name: value for name, value in layer_digests.items() if value is not None
                },
            }
            manifest = dict(old_manifest)
            manifest["artifacts"] = artifacts
            manifest["header_policy"] = "refresh" if refresh_header else "preserve"
            manifest["generation_digest"] = _generation_digest(manifest)
            write_json(stage / MANIFEST_NAME, manifest)
            self._publish_stage(stage, profile=False)

    def _publish_stage(self, stage: Path, *, profile: bool = True) -> None:
        self.layers_dir.mkdir(parents=True, exist_ok=True)
        if profile:
            _replace_file(stage / PROFILE_NAME, self.profile_path)
        for spec in LAYERS:
            _replace_file(stage / LAYERS_DIR_NAME / spec.filename, self.layers_dir / spec.filename)
        _replace_file(stage / MANIFEST_NAME, self.manifest_path)

    def _manifest(
        self,
        *,
        entries_count: int,
        quick: str,
        content: str,
        options: ScanOptions,
        requested_mode: str,
        effective_mode: str,
        gradle_fallback: bool,
        refresh_header: bool,
        artifacts: dict[str, object],
    ) -> dict[str, Any]:
        git = read_git_info(self.repo_root)
        manifest: dict[str, Any] = {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "profile_schema_version": SCHEMA_VERSION,
            "schema_version": SCHEMA_VERSION,
            "output_security_version": OUTPUT_SECURITY_VERSION,
            "generation_contract_version": GENERATION_CONTRACT_VERSION,
            "tool_version": __version__,
            "scanned_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "repo_path": sanitize_snippet(str(self.repo_root)),
            "files_count": entries_count,
            "fingerprint_quick": quick,
            "fingerprint_content": content,
            "scan_options": options.to_dict(),
            "requested_scan_mode": requested_mode,
            "effective_scan_mode": effective_mode,
            "gradle_fallback": gradle_fallback,
            "header_policy": "refresh" if refresh_header else "preserve",
            "artifacts": artifacts,
            "git_commit": git.commit,
            "git_dirty": git.dirty,
            "git_root": git.root,
        }
        manifest["generation_digest"] = _generation_digest(manifest)
        return manifest

    def _updated_metadata_manifest(
        self,
        manifest: dict[str, Any],
        *,
        entries_count: int,
        quick: str,
        content: str,
    ) -> dict[str, Any]:
        git = read_git_info(self.repo_root)
        updated = dict(manifest)
        updated.update(
            {
                "files_count": entries_count,
                "fingerprint_quick": quick,
                "fingerprint_content": content,
                "git_commit": git.commit,
                "git_dirty": git.dirty,
                "git_root": git.root,
            }
        )
        updated["generation_digest"] = _generation_digest(updated)
        return updated

    def _status_from(
        self,
        inspection: CacheInspection,
        *,
        state: State | None = None,
        reason: str | None = None,
        files_count: int,
    ) -> Status:
        try:
            stored_commit = normalize_git_object_id(inspection.manifest.get("git_commit"))
        except ValueError:
            stored_commit = None
        manifest = sanitize_public(inspection.manifest)
        if not isinstance(manifest, dict):
            manifest = {}
        git = read_git_info(self.repo_root)
        changed = (
            changed_files_since(self.repo_root, stored_commit)
            if stored_commit and git.commit
            else None
        )
        options = ScanOptions.from_manifest(manifest.get("scan_options"))
        return Status(
            state=state or inspection.state,
            files_count=files_count,
            repo_path=sanitize_snippet(str(self.repo_root)),
            scanned_at=_as_str(manifest.get("scanned_at")),
            tool_version=_as_str(manifest.get("tool_version")),
            schema_version=_as_int(manifest.get("profile_schema_version"))
            or _as_int(manifest.get("schema_version")),
            git_commit=stored_commit,
            git_dirty=_as_bool(manifest.get("git_dirty")),
            git_root=_as_str(manifest.get("git_root")),
            head_commit=git.commit,
            changed_files=changed,
            reason=reason if reason is not None else inspection.reason,
            scan_mode=_as_str(manifest.get("effective_scan_mode")),
            requested_scan_mode=_as_str(manifest.get("requested_scan_mode")),
            gradle_fallback=_as_bool(manifest.get("gradle_fallback")),
            evidence_limit=options.evidence_limit if options else None,
        )

    def _completed_status(self, action: str, *, authority_change: str | None = None) -> Status:
        return replace(
            self.status(),
            refresh_action=action,
            authority_change=authority_change,
        )

    def _validate_source_references(self, profile: Profile) -> None:
        for _, section in profile.iter_sections():
            evidence_items = list(section.evidence)
            for item in section.inventory_items:
                evidence_items.extend(item.evidence)
            for evidence in evidence_items:
                if evidence.provenance is Provenance.GRADLE_MODEL:
                    continue
                try:
                    checked_path(
                        self.repo_root,
                        evidence.path,
                        directory=evidence.entry_type == "directory",
                    )
                except ValueError:
                    raise FileNotFoundError(
                        "Unsafe cached source reference; run coador scan"
                    ) from None

    def require_profile(self) -> Profile:
        profile = self.load()
        if profile is None:
            raise FileNotFoundError("No knowledge base found; run `coador scan` first")
        return profile

    def list_layers(self) -> list[dict[str, object]]:
        """Return one row per layer: id, title, and how many sections were detected."""
        profile = self.require_profile()
        return [
            {
                "id": layer.id,
                "title": layer.title,
                "sections": len(layer.sections),
                "detected": layer.detected_count,
            }
            for layer in profile.layers
        ]

    def get_layer(self, layer_id: str) -> Layer | None:
        return self.require_profile().layer(layer_id)

    def get_section(self, layer_id: str, section_id: str) -> Section | None:
        return self.require_profile().find_section(layer_id, section_id)

    def get_section_page(
        self,
        layer_id: str,
        section_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = DEFAULT_INVENTORY_PAGE_SIZE,
    ) -> SectionPage | None:
        """Return a safe inventory slice; signals are returned without page metadata."""
        section = self.get_section(layer_id, section_id)
        if section is None:
            return None
        safe_section = Section.from_dict(section.to_dict())
        if safe_section.kind is ResultKind.SIGNAL:
            if cursor is not None:
                raise ValueError("Pagination cursor applies only to inventory sections")
            return SectionPage(safe_section)
        if limit is not None and limit <= 0:
            raise ValueError("Inventory page limit must be positive")

        offset = _inventory_offset(cursor)
        total = len(safe_section.items)
        if offset > total:
            raise ValueError("Inventory cursor is past the end of the section")
        end = total if limit is None else min(total, offset + limit)
        values = safe_section.items[offset:end]
        safe_section.items = values
        safe_section.item_evidence = {
            value: safe_section.item_evidence.get(value, []) for value in values
        }
        return SectionPage(
            section=safe_section,
            offset=offset,
            limit=limit,
            total=total,
            next_cursor=str(end) if end < total else None,
        )

    def search(self, query: str, *, limit: int = 10, layer_id: str | None = None) -> list[Hit]:
        """Rank the sections of the knowledge base against a query."""
        return LexicalRetriever(self.require_profile()).search(
            query, limit=limit, layer_id=layer_id
        )

    def overview(self) -> dict[str, object]:
        """A compact answer to "what is this project", for the first call an agent makes."""
        profile = self.require_profile()
        status = self.status()

        highlights: dict[str, str] = {}
        for layer_id, section_id, label in HIGHLIGHTS:
            section = profile.find_section(layer_id, section_id)
            if section is not None and section.detected:
                highlights[label] = section.summary

        return {
            "project": profile.project_name,
            "state": str(status.state),
            "scanned_at": status.scanned_at,
            "git_commit": status.git_commit,
            "highlights": highlights,
            "layers": [
                {
                    "id": layer.id,
                    "title": layer.title,
                    "detected": layer.detected_count,
                    "sections": len(layer.sections),
                }
                for layer in profile.layers
            ],
            "undetected": [
                f"{layer.id}/{section.id}"
                for layer, section in profile.iter_sections()
                if not section.detected
            ],
        }


def layer_ids() -> tuple[str, ...]:
    return tuple(spec.id for spec in LAYERS)


def _inventory_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor or not cursor.isascii() or not cursor.isdecimal():
        raise ValueError("Invalid inventory cursor")
    offset = int(cursor)
    if str(offset) != cursor:
        raise ValueError("Invalid inventory cursor")
    return offset


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


def _profile_is_complete(profile: Profile) -> bool:
    return tuple(layer.id for layer in profile.layers) == layer_ids()


def _file_digest(root: Path, path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open_source(root, path) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, ValueError):
        return None
    return digest.hexdigest()


def _generated_digest(root: Path, path: Path) -> str | None:
    content = read_text(root, path)
    if content is None:
        return None
    generated = extract_generated(content)
    if generated is None:
        return None
    return hashlib.sha256(generated.encode()).hexdigest()


def _artifact_digests(root: Path, profile_path: Path, layers_dir: Path) -> dict[str, object]:
    profile_digest = _file_digest(root, profile_path)
    layer_digests = {
        spec.filename: _generated_digest(layers_dir, layers_dir / spec.filename) for spec in LAYERS
    }
    if profile_digest is None or any(value is None for value in layer_digests.values()):
        raise RuntimeError("Could not stage a complete knowledge-base generation")
    return {
        PROFILE_NAME: profile_digest,
        LAYERS_DIR_NAME: {
            name: value for name, value in layer_digests.items() if value is not None
        },
    }


def _generation_digest(manifest: dict[str, Any]) -> str:
    fields = (
        "manifest_schema_version",
        "profile_schema_version",
        "schema_version",
        "output_security_version",
        "generation_contract_version",
        "tool_version",
        "files_count",
        "fingerprint_quick",
        "fingerprint_content",
        "scan_options",
        "requested_scan_mode",
        "effective_scan_mode",
        "gradle_fallback",
        "header_policy",
        "artifacts",
    )
    payload = {field: manifest.get(field) for field in fields}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
