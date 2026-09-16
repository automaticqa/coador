"""Repository access rules, separate from operational output-directory paths.

Source references use POSIX spelling. Symlinks (including internal links) are
not scanned. The selected root itself is resolved once by the caller.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PureWindowsPath
from typing import BinaryIO


class UnsafePathError(ValueError):
    """A source reference is outside the supported repository boundary."""


def normalize_reference(value: str, *, directory: bool = False) -> str:
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise UnsafePathError("Invalid source reference")
    windows = PureWindowsPath(value)
    if windows.drive or windows.root or value.startswith("/"):
        raise UnsafePathError("Absolute source references are not supported")
    parts = value.replace("\\", "/").split("/")
    if ".." in parts or any(":" in part for part in parts):
        raise UnsafePathError("Escaping source references are not supported")
    result = "/".join(part for part in parts if part not in ("", "."))
    if not result:
        if directory:
            return "."
        raise UnsafePathError("A file reference is required")
    return result


def checked_path(root: Path, path: Path | str, *, directory: bool = False) -> Path:
    """Check a reference or internal absolute Path without following links."""
    root = root.absolute()
    if isinstance(path, Path) and path.is_absolute():
        try:
            reference = path.relative_to(root).as_posix()
        except ValueError:
            raise UnsafePathError("Source is outside the repository") from None
    else:
        reference = str(path)
    reference = normalize_reference(reference, directory=directory)
    candidate = root
    for part in reference.split("/"):
        candidate = candidate / part
        if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
            raise UnsafePathError("Linked source entries are not supported")
        try:
            if getattr(candidate.lstat(), "st_file_attributes", 0) & 0x400:
                raise UnsafePathError("Reparse points are not supported")
        except FileNotFoundError:
            pass
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, RuntimeError):
        raise UnsafePathError("Source is outside the repository") from None
    return candidate


def open_source(root: Path, path: Path | str) -> BinaryIO:
    """Open a regular source file, refusing links in every component on POSIX."""
    candidate = checked_path(root, path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            parts = candidate.relative_to(root.absolute()).parts
            for part in parts[:-1]:
                next_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
                )
                os.close(directory_fd)
                directory_fd = next_fd
            descriptor = os.open(parts[-1], flags, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
    else:
        descriptor = os.open(candidate, flags)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise UnsafePathError("Source must be a regular file")
    return os.fdopen(descriptor, "rb")


def read_text(root: Path, path: Path | str) -> str | None:
    try:
        with open_source(root, path) as handle:
            return (
                handle.read()
                .decode("utf-8", errors="replace")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
    except (OSError, UnsafePathError):
        return None
