"""Detector contract: evidence, detection results and the base detector class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from coador.fileindex import active_index, get_index
from coador.model import Evidence as SourceEvidence
from coador.model import InventoryCompleteness, Provenance
from coador.paths import checked_path
from coador.redact import sanitize_snippet


@dataclass(frozen=True)
class Evidence:
    file_path: str
    line_start: int
    line_end: int
    snippet: str
    provenance: Provenance = Provenance.FILE
    exact: SourceEvidence | None = None

    def to_markdown(self) -> str:
        snippet = sanitize_snippet(self.snippet)
        if self.provenance is Provenance.FILE:
            return f"`{self.file_path}` - {snippet}"
        if self.exact is None:
            return "Unverified source evidence omitted"
        if self.line_start == self.line_end:
            return f"`{self.file_path}:{self.line_start}` - {snippet}"
        return f"`{self.file_path}:{self.line_start}-{self.line_end}` - {snippet}"

    @classmethod
    def from_match(
        cls,
        file_path: str,
        line_number: int,
        snippet: str,
        context_lines: int = 0,
    ) -> Evidence:
        sanitized = sanitize_snippet(snippet)
        index = active_index.get()
        exact = (
            index.exact(file_path, line_number, line_number + context_lines, snippet)
            if index
            else None
        )
        return cls(
            file_path=file_path,
            line_start=line_number,
            line_end=line_number + context_lines,
            snippet=sanitized.strip(),
            provenance=Provenance.SOURCE_LINES,
            exact=exact,
        )


@dataclass
class DetectionResult:
    detected: bool
    description: str
    evidence: list[Evidence] = field(default_factory=list)
    items: list[str] | None = None
    item_evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    inventory_completeness: InventoryCompleteness | None = None
    collection_limit: int | None = None
    collection_stop_reason: str | None = None
    error: str | None = None
    limitations: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = []
        if self.detected:
            lines.append(f"**Detected:** {self.description}")
        else:
            lines.append(f"**Not found:** {self.description}")

        if self.evidence:
            lines.append("")
            lines.append("**Evidence:**")
            for ev in self.evidence:
                lines.append(f"- {ev.to_markdown()}")

        return "\n".join(lines)

    @classmethod
    def not_found(cls, description: str = "No signals detected") -> DetectionResult:
        return cls(detected=False, description=description, evidence=[])

    @classmethod
    def inventory(
        cls,
        description: str,
        findings: Iterable[tuple[str, Evidence]],
        *,
        completeness: InventoryCompleteness,
        collection_limit: int | None = None,
        stop_reason: str | None = None,
        limitations: Iterable[str] = (),
    ) -> DetectionResult:
        """Build a deduplicated inventory without separating values from provenance."""
        items: list[str] = []
        evidence: list[Evidence] = []
        item_evidence: dict[str, list[Evidence]] = {}
        for value, item in findings:
            safe_value = sanitize_snippet(value)
            if safe_value not in item_evidence:
                items.append(safe_value)
                item_evidence[safe_value] = []
            if item not in item_evidence[safe_value]:
                item_evidence[safe_value].append(item)
            evidence.append(item)
        return cls(
            detected=bool(items),
            description=description,
            evidence=evidence,
            items=items,
            item_evidence=item_evidence,
            inventory_completeness=completeness,
            collection_limit=collection_limit,
            collection_stop_reason=stop_reason,
            limitations=list(limitations),
        )


class BaseDetector(ABC):
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def detect(self) -> DetectionResult: ...

    def relative_path(self, path: Path) -> str:
        return (
            checked_path(self.repo_root, path, directory=True)
            .relative_to(self.repo_root)
            .as_posix()
        )

    def find_file(self, *names: str) -> Path | None:
        return get_index(self.repo_root).find(*names)

    def glob(self, pattern: str | Iterable[str]) -> list[Path]:
        return get_index(self.repo_root).glob(pattern)

    def find_dirs(self, dir_names: Iterable[str]) -> list[Path]:
        return get_index(self.repo_root).find_dirs(dir_names)

    def read_file(self, path: Path) -> str | None:
        from coador.textscan import read_file_content

        return read_file_content(path, root=self.repo_root)

    def source_evidence(self, path: Path, start: int, end: int, value: str) -> Evidence:
        """Keep an inventory value separate from the captured source quotation."""
        reference = self.relative_path(path)
        exact = get_index(self.repo_root).exact(reference, start, end, "")
        return Evidence(
            reference,
            start,
            end,
            sanitize_snippet(value),
            provenance=Provenance.SOURCE_LINES,
            exact=exact,
        )
