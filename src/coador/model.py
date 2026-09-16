"""The knowledge-base data model.

A scan produces a :class:`Profile`: layers, each holding the sections that the
detectors of that layer produced. The profile is the single source of truth -
``profile.json`` is written from it and the Markdown layers are a projection of
it, so no component ever has to parse generated Markdown back into data.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from coador.paths import normalize_reference
from coador.redact import sanitize_snippet

SCHEMA_VERSION = 3


class SchemaMismatchError(ValueError):
    """The stored profile predates or exceeds the supported provenance contract."""


class Provenance(StrEnum):
    SOURCE_LINES = "source_lines"
    FILE = "file"
    GRADLE_MODEL = "gradle_model"


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid model identifier")
    return value


class ResultKind(StrEnum):
    """How a section should be read.

    ``SIGNAL`` sections answer "is this used here, and where"; their evidence is
    a sample and is capped. ``INVENTORY`` sections answer "list all of them" -
    deep links, test tags, modules - and are never truncated.
    """

    SIGNAL = "signal"
    INVENTORY = "inventory"


class InventoryCompleteness(StrEnum):
    """Whether an inventory covers its declared source boundary."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class Source(StrEnum):
    """Where a section's information came from."""

    HEURISTIC = "heuristic"
    GRADLE = "gradle"


@dataclass(frozen=True)
class Evidence:
    """A single file location backing a claim."""

    path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    snippet: str = ""
    provenance: Provenance = Provenance.SOURCE_LINES
    entry_type: str = "file"
    project: str | None = None
    property: str | None = None
    source_line_count: int | None = None
    source_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "snippet", sanitize_snippet(self.snippet))
        if self.project is not None:
            object.__setattr__(self, "project", sanitize_snippet(self.project))
        if self.property is not None:
            object.__setattr__(self, "property", sanitize_snippet(self.property))

    def validate(self) -> None:
        if self.provenance is Provenance.GRADLE_MODEL:
            if self.path or not self.project or not self.property:
                raise ValueError("Invalid Gradle provenance")
            if self.line_start is not None or self.line_end is not None:
                raise ValueError("Model facts cannot claim source lines")
        else:
            if self.entry_type not in ("file", "directory"):
                raise ValueError("Invalid source entry type")
            normalize_reference(self.path, directory=self.entry_type == "directory")
            if sanitize_snippet(self.path) != self.path:
                raise ValueError("Sensitive source reference omitted")
            if self.provenance is Provenance.SOURCE_LINES:
                if self.entry_type != "file" or any(
                    type(n) is not int
                    for n in (self.line_start, self.line_end, self.source_line_count)
                ):
                    raise ValueError("Exact evidence requires snapshot bounds")
                assert (
                    self.line_start is not None
                    and self.line_end is not None
                    and self.source_line_count is not None
                )
                if not 1 <= self.line_start <= self.line_end <= self.source_line_count:
                    raise ValueError("Invalid source range")
                if not self.source_digest or not re.fullmatch(r"[a-f0-9]{64}", self.source_digest):
                    raise ValueError("Exact evidence requires a content digest")
            elif self.line_start is not None or self.line_end is not None:
                raise ValueError("File facts cannot claim source lines")

    @classmethod
    def from_source(cls, path: str, content: str, start: int, end: int | None = None) -> Self:
        end = start if end is None else end
        lines = content.splitlines()
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError("Invalid source range")
        result = cls(
            path=normalize_reference(path),
            line_start=start,
            line_end=end,
            snippet="\n".join(sanitize_snippet(content).splitlines()[start - 1 : end]).strip(),
            source_line_count=len(lines),
            source_digest=hashlib.sha256(content.encode()).hexdigest(),
        )
        result.validate()
        return result

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        data: dict[str, Any] = {
            "provenance": self.provenance.value,
            "snippet": sanitize_snippet(self.snippet),
        }
        if self.provenance is Provenance.GRADLE_MODEL:
            data.update(
                project=sanitize_snippet(self.project or ""),
                property=sanitize_snippet(self.property or ""),
            )
        else:
            data.update(
                path=normalize_reference(self.path, directory=self.entry_type == "directory"),
                entry_type=self.entry_type,
            )
            if self.provenance is Provenance.SOURCE_LINES:
                data.update(
                    line_start=self.line_start,
                    line_end=self.line_end,
                    source_line_count=self.source_line_count,
                    source_digest=self.source_digest,
                )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        result = cls(
            path=data.get("path", ""),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            snippet=sanitize_snippet(str(data.get("snippet", ""))),
            provenance=Provenance(data["provenance"]),
            entry_type=data.get("entry_type", "file"),
            project=data.get("project"),
            property=data.get("property"),
            source_line_count=data.get("source_line_count"),
            source_digest=data.get("source_digest"),
        )
        result.validate()
        return result


@dataclass
class InventoryItem:
    """One deduplicated inventory value and every accepted fact supporting it."""

    value: str
    evidence: list[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.value = sanitize_snippet(self.value)
        self.evidence = list(dict.fromkeys(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": sanitize_snippet(self.value),
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            value=str(data["value"]),
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
        )


@dataclass
class Section:
    """One detector's finding inside a layer."""

    id: str
    title: str
    detected: bool
    summary: str
    kind: ResultKind = ResultKind.SIGNAL
    source: Source = Source.HEURISTIC
    evidence: list[Evidence] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    item_evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    inventory_completeness: InventoryCompleteness | None = None
    collection_limit: int | None = None
    collection_stop_reason: str | None = None
    evidence_total: int = 0
    error: str | None = None
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _identifier(self.id)
        self.summary = sanitize_snippet(self.summary)
        self.title = sanitize_snippet(self.title)
        self.items = list(dict.fromkeys(sanitize_snippet(item) for item in self.items))
        accepted = set(self.items)
        normalized_evidence: dict[str, list[Evidence]] = {}
        for value, evidence in self.item_evidence.items():
            safe_value = sanitize_snippet(value)
            if safe_value in accepted and evidence:
                normalized_evidence.setdefault(safe_value, [])
                for item in evidence:
                    if item not in normalized_evidence[safe_value]:
                        normalized_evidence[safe_value].append(item)
        self.item_evidence = normalized_evidence
        if not self.is_signal and self.inventory_completeness is None:
            self.inventory_completeness = InventoryCompleteness.UNKNOWN
        if self.collection_limit is not None and self.collection_limit <= 0:
            raise ValueError("Collection limit must be positive")
        if self.collection_stop_reason is not None:
            self.collection_stop_reason = sanitize_snippet(self.collection_stop_reason)
        if (
            self.inventory_completeness is InventoryCompleteness.INCOMPLETE
            and not self.collection_stop_reason
        ):
            raise ValueError("Incomplete inventory requires a stop reason")
        if (
            self.inventory_completeness is not InventoryCompleteness.INCOMPLETE
            and self.collection_stop_reason is not None
        ):
            raise ValueError("Only an incomplete inventory can have a stop reason")
        if self.error is not None:
            self.error = sanitize_snippet(self.error)
        self.limitations = list(
            dict.fromkeys(sanitize_snippet(limitation) for limitation in self.limitations)
        )
        if not self.evidence_total:
            self.evidence_total = len(self.evidence) if self.is_signal else len(self.items)

    @property
    def is_signal(self) -> bool:
        return self.kind is ResultKind.SIGNAL

    @property
    def truncated(self) -> bool:
        """True when evidence was capped and the full count is larger."""
        return self.is_signal and self.evidence_total > len(self.evidence)

    @property
    def inventory_items(self) -> list[InventoryItem]:
        """Return item records without giving up the convenient string item API."""
        return [
            InventoryItem(value=value, evidence=self.item_evidence.get(value, []))
            for value in self.items
        ]

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": _identifier(self.id),
            "title": sanitize_snippet(self.title),
            "detected": self.detected,
            "summary": sanitize_snippet(self.summary),
            "kind": self.kind.value,
            "source": self.source.value,
            "evidence_total": self.evidence_total,
        }
        if not self.is_signal:
            data.update(
                items=[item.to_dict() for item in self.inventory_items],
                inventory_completeness=(
                    self.inventory_completeness or InventoryCompleteness.UNKNOWN
                ).value,
                collection_limit=self.collection_limit,
                collection_stop_reason=self.collection_stop_reason,
            )
        if self.evidence:
            data["evidence"] = [item.to_dict() for item in self.evidence]
        if self.error is not None:
            data["error"] = sanitize_snippet(self.error)
        if self.limitations:
            data["limitations"] = [sanitize_snippet(item) for item in self.limitations]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
            raise ValueError("Invalid inventory items")
        inventory_items = [InventoryItem.from_dict(item) for item in raw_items]
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            detected=bool(data["detected"]),
            summary=str(data["summary"]),
            kind=ResultKind(data.get("kind", ResultKind.SIGNAL.value)),
            source=Source(data.get("source", Source.HEURISTIC.value)),
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            items=[item.value for item in inventory_items],
            item_evidence={item.value: item.evidence for item in inventory_items},
            inventory_completeness=(
                InventoryCompleteness(data["inventory_completeness"])
                if data.get("kind", ResultKind.SIGNAL.value) == ResultKind.INVENTORY.value
                else None
            ),
            collection_limit=data.get("collection_limit"),
            collection_stop_reason=data.get("collection_stop_reason"),
            evidence_total=int(data.get("evidence_total", 0)),
            error=data.get("error"),
            limitations=[str(item) for item in data.get("limitations", [])],
        )


@dataclass
class Layer:
    """One Markdown layer: a themed group of sections."""

    id: str
    title: str
    sections: list[Section] = field(default_factory=list)

    def __post_init__(self) -> None:
        _identifier(self.id)
        self.title = sanitize_snippet(self.title)

    @property
    def detected_count(self) -> int:
        return sum(1 for section in self.sections if section.detected)

    def section(self, section_id: str) -> Section | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": _identifier(self.id),
            "title": sanitize_snippet(self.title),
            "sections": [section.to_dict() for section in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            sections=[Section.from_dict(item) for item in data.get("sections", [])],
        )


@dataclass
class Profile:
    """Everything the scanner learned about one repository."""

    project_name: str
    layers: list[Layer] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.project_name = sanitize_snippet(self.project_name)

    def layer(self, layer_id: str) -> Layer | None:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def find_section(self, layer_id: str, section_id: str) -> Section | None:
        layer = self.layer(layer_id)
        return layer.section(section_id) if layer else None

    def iter_sections(self) -> list[tuple[Layer, Section]]:
        return [(layer, section) for layer in self.layers for section in layer.sections]

    def to_dict(self) -> dict[str, Any]:
        if self.schema_version != SCHEMA_VERSION:
            raise SchemaMismatchError("Incompatible profile schema; run coador scan --force")
        return {
            "schema_version": self.schema_version,
            "project": {"name": sanitize_snippet(self.project_name)},
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        project = data.get("project", {})
        if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
            raise SchemaMismatchError("Incompatible profile schema; run coador scan --force")
        return cls(
            project_name=str(project.get("name", "")),
            layers=[Layer.from_dict(item) for item in data.get("layers", [])],
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )
