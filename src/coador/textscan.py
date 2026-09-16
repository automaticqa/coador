"""Text search over the indexed repository files."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from coador.fileindex import get_index
from coador.redact import sanitize_snippet

# A detector that matches thousands of lines does not become more convincing
# past the first few dozen; the cap keeps both the scan and the output bounded.
DEFAULT_MAX_MATCHES = 200


@dataclass
class GrepMatch:
    file_path: Path
    line_number: int
    line_content: str
    match_text: str


def read_file_content(path: Path, *, root: Path) -> str | None:
    index = get_index(root)
    content = index.read(path)
    return index.sanitized(content) if content is not None else None


def read_lines(path: Path, *, root: Path) -> list[str]:
    content = read_file_content(path, root=root)
    return content.splitlines() if content is not None else []


def glob_files(root: Path, patterns: str | Iterable[str]) -> list[Path]:
    """Return files under ``root`` matching one or more glob patterns."""
    return get_index(root).glob(patterns)


def grep_files(
    root: Path,
    pattern: str | re.Pattern[str],
    file_glob: str | Iterable[str] = "**/*",
    max_matches: int = DEFAULT_MAX_MATCHES,
    *,
    multiline: bool = False,
    all_matches_per_line: bool = False,
) -> list[GrepMatch]:
    """Search ``pattern`` in the files matching ``file_glob``.

    By default the search is line oriented. With ``multiline=True`` the pattern
    is matched against the whole file, so patterns spanning several lines (a
    YAML key followed by its block, say) work as written.
    """
    index = get_index(root)
    matches: list[GrepMatch] = []

    if multiline:
        regex = (
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            if isinstance(pattern, str)
            else pattern
        )
        for file_path in index.glob(file_glob):
            if len(matches) >= max_matches:
                break
            content = index.read(file_path)
            if not content:
                continue
            for match in regex.finditer(content):
                if len(matches) >= max_matches:
                    break
                line_number = content.count("\n", 0, match.start()) + 1
                end_number = content.count("\n", 0, max(match.start(), match.end() - 1)) + 1
                index.remember_match(file_path, content, line_number, end_number)
                line_content = index.sanitized_lines(content)[line_number - 1].strip()
                matches.append(
                    GrepMatch(
                        file_path=file_path,
                        line_number=line_number,
                        line_content=line_content,
                        match_text=line_content,
                    )
                )
        return matches

    line_regex = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
    for file_path in index.glob(file_glob):
        if len(matches) >= max_matches:
            break
        content = index.read(file_path)
        if content is None:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            if len(matches) >= max_matches:
                break
            found_matches = (
                line_regex.finditer(line)
                if all_matches_per_line
                else iter([found] if (found := line_regex.search(line)) else [])
            )
            for found in found_matches:
                if len(matches) >= max_matches:
                    break
                index.remember_match(file_path, content, number, number)
                matches.append(
                    GrepMatch(
                        file_path=file_path,
                        line_number=number,
                        line_content=index.sanitized_lines(content)[number - 1].strip(),
                        match_text=sanitize_snippet(found.group(0)),
                    )
                )

    return matches
