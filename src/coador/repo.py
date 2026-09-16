"""Repository file discovery: exclusion rules, walking, globbing and Gradle root lookup."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from coador.paths import UnsafePathError, checked_path
from coador.redact import sanitize_snippet

EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".gradle",
        ".idea",
        "build",
        "node_modules",
        ".cxx",
        ".kotlin",
        ".coador",
    }
)

EXCLUDE_EXTS: frozenset[str] = frozenset(
    {
        ".apk",
        ".aab",
        ".jar",
        ".class",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".mp4",
        ".mov",
        ".zip",
        ".rar",
        ".webp",
        ".ico",
    }
)

SETTINGS_FILES: tuple[str, ...] = ("settings.gradle.kts", "settings.gradle")

logger = logging.getLogger(__name__)


def is_excluded_dir(name: str) -> bool:
    return name in EXCLUDE_DIRS


def is_excluded_file(path: Path) -> bool:
    return path.suffix.lower() in EXCLUDE_EXTS


def normalize_excluded_paths(
    root: Path, excluded_paths: Iterable[Path] | None = None
) -> tuple[Path, ...]:
    """Return deterministic exclusions contained by ``root``.

    Relative exclusions are interpreted from the repository root. Paths outside
    the root cannot affect discovery and are ignored.
    """
    root = root.resolve()
    normalized: set[Path] = set()
    for path in excluded_paths or ():
        candidate = path if path.is_absolute() else root / path
        try:
            candidate = candidate.resolve()
            candidate.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        normalized.add(candidate)
    ordered = sorted(normalized, key=lambda path: (len(path.parts), path.as_posix()))
    minimal: list[Path] = []
    for candidate in ordered:
        if not any(parent == candidate or parent in candidate.parents for parent in minimal):
            minimal.append(candidate)
    return tuple(minimal)


def _is_excluded_path(path: Path, excluded_paths: tuple[Path, ...]) -> bool:
    return any(path == excluded or excluded in path.parents for excluded in excluded_paths)


def discover_paths(
    root: Path,
    extensions: Iterable[str] | None = None,
    exclude_dirs: Iterable[str] | None = None,
    excluded_paths: Iterable[Path] | None = None,
) -> tuple[list[Path], list[Path]]:
    """Collect scannable files and directories with one repository walk."""
    root = root.resolve()
    ext_set = set(extensions) if extensions else None
    excl_dirs = set(exclude_dirs) if exclude_dirs else EXCLUDE_DIRS
    path_exclusions = normalize_excluded_paths(root, excluded_paths)
    files: list[Path] = []
    directories: list[Path] = []

    if _is_excluded_path(root, path_exclusions):
        return files, directories

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in excl_dirs
            and not _is_excluded_path(current / name, path_exclusions)
            and safe_entry(root, current / name)
        ]
        directories.extend(current / name for name in dirnames)

        for name in filenames:
            path = current / name
            if _is_excluded_path(path, path_exclusions) or not safe_entry(root, path):
                continue
            if not path.is_file() or is_excluded_file(path):
                continue
            if ext_set and path.suffix.lower() not in ext_set:
                continue
            files.append(path)

    return files, directories


def iter_files(
    root: Path,
    extensions: Iterable[str] | None = None,
    exclude_dirs: Iterable[str] | None = None,
    excluded_paths: Iterable[Path] | None = None,
) -> Iterator[Path]:
    """Walk ``root`` depth-first, pruning excluded directories and skipping binary files."""
    files, _ = discover_paths(root, extensions, exclude_dirs, excluded_paths)
    yield from files


def find_dirs(
    root: Path,
    dir_names: Iterable[str],
    excluded_paths: Iterable[Path] | None = None,
) -> list[Path]:
    """Return sorted directories whose name is in ``dir_names``."""
    name_set = set(dir_names)
    _, directories = discover_paths(root, excluded_paths=excluded_paths)
    return sorted(path for path in directories if path.name in name_set)


def has_settings_file(directory: Path) -> bool:
    return any(
        safe_entry(directory, directory / name) and (directory / name).is_file()
        for name in SETTINGS_FILES
    )


def safe_entry(root: Path, path: Path) -> bool:
    try:
        checked_path(root, path, directory=True)
        return True
    except (UnsafePathError, OSError):
        return False


def find_gradle_roots(search_dir: Path) -> list[Path]:
    """Return every directory under ``search_dir`` that holds a Gradle settings file.

    Results are ordered by distance from ``search_dir`` and then alphabetically,
    so the first entry is the nearest candidate.
    """
    roots: list[Path] = []

    if has_settings_file(search_dir):
        roots.append(search_dir)

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = sorted(
            d for d in dirs if not is_excluded_dir(d) and safe_entry(search_dir, Path(root) / d)
        )
        current = Path(root)
        if current == search_dir:
            continue
        if any(name in files for name in SETTINGS_FILES) and has_settings_file(current):
            roots.append(current)

    roots.sort(key=lambda path: (len(path.relative_to(search_dir).parts), path.as_posix()))
    return roots


def find_repo_root(search_dir: Path) -> Path | None:
    """Locate the nearest Gradle project root under ``search_dir``.

    When several candidates exist the nearest one wins and the others are
    reported on the log, because picking silently is how a scan ends up
    describing a sample app instead of the real project.
    """
    if has_settings_file(search_dir):
        return search_dir

    roots = find_gradle_roots(search_dir)
    if not roots:
        return None

    chosen = roots[0]
    if len(roots) > 1:
        others = ", ".join(str(path) for path in roots[1:5])
        suffix = ", ..." if len(roots) > 5 else ""
        logger.warning(
            "Multiple Gradle roots found; using the nearest one: %s (others: %s%s)",
            sanitize_snippet(str(chosen)),
            sanitize_snippet(others),
            suffix,
        )
    return chosen
