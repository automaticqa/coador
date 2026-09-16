"""A single walk of the repository, shared by every detector.

Detectors ask the same tree the same questions over and over: "give me every
``**/build.gradle.kts``", "search this regex in ``**/androidTest/**/*.kt``".
Walking the tree per question is what made a scan of a large repository take
tens of seconds. :class:`FileIndex` walks once, keeps the relative paths, and
caches the text of the files that were actually read.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable, Sequence
from contextvars import ContextVar
from pathlib import Path

from coador.model import Evidence
from coador.paths import checked_path, read_text
from coador.redact import sanitize_snippet
from coador.repo import discover_paths, normalize_excluded_paths

logger = logging.getLogger(__name__)

# Text that is cached in memory; larger files are read on demand and not kept.
MAX_CACHED_FILE_BYTES = 1024 * 1024
MAX_CACHE_BYTES = 256 * 1024 * 1024


def translate_glob(pattern: str) -> re.Pattern[str]:
    """Translate a pathlib-style glob into a regular expression.

    ``**`` matches any number of directories (including none), ``*`` matches
    within one path segment and ``?`` matches a single character.
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            parts.append("(?:[^/]+/)*")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif char == "*":
            parts.append("[^/]*")
            index += 1
        elif char == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(char))
            index += 1
    return re.compile("".join(parts) + r"\Z")


class FileIndex:
    """An immutable snapshot of the scannable files under a repository root."""

    def __init__(
        self,
        root: Path,
        paths: Sequence[Path],
        directories: Sequence[Path] = (),
        excluded_paths: Sequence[Path] = (),
    ) -> None:
        self.root = root
        self._paths: tuple[Path, ...] = tuple(paths)
        self._directories: tuple[Path, ...] = tuple(directories)
        self.excluded_paths: tuple[Path, ...] = tuple(excluded_paths)
        self._relative: tuple[str, ...] = tuple(
            path.relative_to(root).as_posix() for path in self._paths
        )
        self._text: dict[Path, str | None] = {}
        self._cached_bytes = 0
        self._matches: dict[tuple[str, int], Evidence] = {}
        self._verified: set[Evidence] = set()
        self._current_text: str | None = None
        self._current_safe = ""
        self._current_lines: list[str] = []
        self._current_count = 0
        self._current_digest = ""

    @classmethod
    def build(cls, root: Path, excluded_paths: Iterable[Path] | None = None) -> FileIndex:
        root = root.resolve()
        exclusions = normalize_excluded_paths(root, excluded_paths)
        paths, directories = discover_paths(root, excluded_paths=exclusions)
        paths.sort()
        directories.sort()
        logger.debug("Indexed %d source files", len(paths))
        return cls(root, paths, directories, exclusions)

    def __len__(self) -> int:
        return len(self._paths)

    @property
    def paths(self) -> tuple[Path, ...]:
        return self._paths

    def relative(self, path: Path) -> str:
        return checked_path(self.root, path).relative_to(self.root.absolute()).as_posix()

    def glob(self, patterns: str | Iterable[str]) -> list[Path]:
        """Return the indexed files matching any of ``patterns``, in path order."""
        if isinstance(patterns, str):
            patterns = (patterns,)
        regexes = [translate_glob(pattern) for pattern in patterns]
        if not regexes:
            return []
        return [
            path
            for path, relative in zip(self._paths, self._relative, strict=True)
            if any(regex.match(relative) for regex in regexes)
        ]

    def find_dirs(self, dir_names: Iterable[str]) -> list[Path]:
        """Return indexed directories whose name is in ``dir_names``."""
        name_set = set(dir_names)
        return [path for path in self._directories if path.name in name_set]

    def read(self, path: Path) -> str | None:
        """Return the text of ``path``, caching files small enough to keep."""
        if path in self._text:
            return self._text[path]

        text = read_text(self.root, path)

        small_enough = text is None or len(text) <= MAX_CACHED_FILE_BYTES
        if small_enough and self._cached_bytes < MAX_CACHE_BYTES:
            self._text[path] = text
            self._cached_bytes += len(text) if text else 0
        return text

    def lines(self, path: Path) -> list[str]:
        text = self.read(path)
        return text.splitlines() if text is not None else []

    def remember_match(self, path: Path, content: str, start: int, end: int) -> None:
        relative = self.relative(path)
        self.sanitized(content)
        evidence = Evidence(
            path=relative,
            line_start=start,
            line_end=end,
            snippet="\n".join(self._current_lines[start - 1 : end]).strip(),
            source_line_count=self._current_count,
            source_digest=self._current_digest,
        )
        evidence.validate()
        self._matches[(relative, start)] = evidence

    def sanitized(self, content: str) -> str:
        if content is not self._current_text:
            self._current_text = content
            self._current_safe = sanitize_snippet(content)
            self._current_lines = self._current_safe.splitlines()
            self._current_count = len(content.splitlines())
            self._current_digest = hashlib.sha256(content.encode()).hexdigest()
        return self._current_safe

    def sanitized_lines(self, content: str) -> list[str]:
        self.sanitized(content)
        return self._current_lines

    def exact(self, reference: str, start: int, end: int, snippet: str) -> Evidence | None:
        """Use captured matches/cached content; never reopen a source for validation."""
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            return None
        path = checked_path(self.root, reference)
        relative = self.relative(path)
        evidence = self._matches.get((relative, start))
        if evidence is None or (end != start and end != evidence.line_end):
            content = self._text.get(path)
            if content is None:
                return None
            try:
                evidence = Evidence.from_source(relative, content, start, end)
            except ValueError:
                return None
        if sanitize_snippet(snippet).strip() not in evidence.snippet:
            return None
        self._verified.add(evidence)
        return evidence

    def verifies(self, evidence: Evidence) -> bool:
        """Only locations actually constructed from this scan's content qualify."""
        return evidence in self._verified


_cache: dict[tuple[Path, tuple[Path, ...]], FileIndex] = {}
active_index: ContextVar[FileIndex | None] = ContextVar("active_source_index", default=None)


def get_index(root: Path, excluded_paths: Iterable[Path] | None = None) -> FileIndex:
    """Return the index for ``root``, building it on first use within a scan."""
    root = root.resolve()
    current = active_index.get()
    if current is not None and current.root == root:
        return current

    exclusions = normalize_excluded_paths(root, excluded_paths)
    key = (root, exclusions)
    index = _cache.get(key)
    if index is None:
        index = FileIndex.build(root, exclusions)
        _cache[key] = index
    return index


def invalidate(root: Path | None = None) -> None:
    """Drop cached indexes; called at the start of every scan."""
    if root is None:
        _cache.clear()
    else:
        resolved = root.resolve()
        for key in [key for key in _cache if key[0] == resolved]:
            _cache.pop(key)
