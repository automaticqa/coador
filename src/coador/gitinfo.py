"""Read-only git metadata about the scanned repository.

The knowledge base records which commit it was built from, so a stale knowledge
base can be reported precisely. Queries are scoped to the scanned directory: a
project vendored inside a larger repository must not report that repository's
unrelated changes. Every call is read-only and degrades to ``None`` when git is
unavailable or the path is not a work tree.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from coador.redact import sanitize_snippet

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_OBJECT_ID_RE = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")


@dataclass(frozen=True)
class GitInfo:
    """The commit a scan was taken at, and whether that tree was clean."""

    commit: str | None
    dirty: bool | None
    root: str | None = None

    @property
    def available(self) -> bool:
        return self.commit is not None

    def is_repository_root(self, path: Path) -> bool:
        """True when ``path`` is the root of the work tree, not a directory inside it."""
        return self.root is not None and Path(self.root) == path


UNAVAILABLE = GitInfo(commit=None, dirty=None, root=None)


def normalize_git_object_id(value: object) -> str | None:
    """Return a complete lowercase Git object ID, allowing an absent value."""
    if value is None:
        return None
    if not isinstance(value, str) or _OBJECT_ID_RE.fullmatch(value) is None:
        raise ValueError("Invalid Git object ID")
    return value.lower()


def _run_git(repo_root: Path, *args: str) -> str | None:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("Git metadata unavailable")
        return None
    if completed.returncode != 0:
        logger.debug("Git metadata query exited with %d", completed.returncode)
        return None
    return completed.stdout


def read_git_info(repo_root: Path) -> GitInfo:
    """Return the current commit, work-tree root, and whether ``repo_root`` has local changes."""
    raw_commit = _run_git(repo_root, "rev-parse", "HEAD")
    if raw_commit is None:
        return UNAVAILABLE
    try:
        commit = normalize_git_object_id(raw_commit.strip())
    except ValueError:
        return UNAVAILABLE
    assert commit is not None

    toplevel = _run_git(repo_root, "rev-parse", "--show-toplevel")
    status = _run_git(repo_root, "status", "--porcelain", "--", str(repo_root))
    return GitInfo(
        commit=commit,
        dirty=None if status is None else bool(status.strip()),
        root=sanitize_snippet(toplevel.strip()) if toplevel else None,
    )


def changed_files_since(repo_root: Path, commit: object) -> int | None:
    """Count files under ``repo_root`` that differ between ``commit`` and the work tree."""
    try:
        object_id = normalize_git_object_id(commit)
    except ValueError:
        return None
    if object_id is None:
        return None
    output = _run_git(repo_root, "diff", "--name-only", object_id, "--", str(repo_root))
    if output is None:
        return None
    return len([line for line in output.splitlines() if line.strip()])
