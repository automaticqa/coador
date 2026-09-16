"""Repository fingerprints used to skip re-scans of an unchanged tree.

Two fingerprints are kept. The *quick* one hashes path, size and modification
time and needs no file reads; it answers "nothing moved" in a fraction of a
second. The *content* one hashes every byte of every file and is computed only
when the quick fingerprint changed, so that a fresh checkout or an ``rsync``
that only rewrote timestamps does not force a rescan.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from coador.paths import UnsafePathError, open_source
from coador.repo import iter_files

CONTENT_READ_BYTES = 64 * 1024


@dataclass(frozen=True)
class FileEntry:
    path: Path
    relative_path: str
    size: int
    mtime_ns: int
    root: Path | None = None


def collect_entries(
    repo_root: Path, excluded_paths: Iterable[Path] | None = None
) -> list[FileEntry]:
    """Stat every scanned file once, sorted by repository-relative path."""
    repo_root = repo_root.resolve()
    entries = []
    for path in iter_files(repo_root, excluded_paths=excluded_paths):
        stat = path.stat()
        entries.append(
            FileEntry(
                path=path,
                relative_path=path.relative_to(repo_root).as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                root=repo_root,
            )
        )
    entries.sort(key=lambda entry: entry.relative_path)
    return entries


def quick_fingerprint(entries: Iterable[FileEntry]) -> str:
    """Hash path, size and modification time without reading file contents."""
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(f"{entry.relative_path}\0{entry.size}\0{entry.mtime_ns}\n".encode())
    return digest.hexdigest()


def content_fingerprint(entries: Iterable[FileEntry]) -> str:
    """Hash path, size and the complete contents of every safely opened file."""
    digest = hashlib.sha256()
    for entry in entries:
        content = hashlib.sha256()
        try:
            with open_source(entry.root or entry.path.parent, entry.path) as handle:
                while chunk := handle.read(CONTENT_READ_BYTES):
                    content.update(chunk)
        except (OSError, UnsafePathError):
            content = hashlib.sha256(b"<unreadable>")
        digest.update(f"{entry.relative_path}\0{entry.size}\0{content.hexdigest()}\n".encode())
    return digest.hexdigest()
