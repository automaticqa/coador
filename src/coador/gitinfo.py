"""Read-only git metadata about the scanned repository.

The knowledge base records which commit it was built from, so a stale knowledge
base can be reported precisely. Queries are scoped to the scanned directory: a
project vendored inside a larger repository must not report that repository's
unrelated changes. Every call is read-only and degrades to ``None`` when git is
unavailable or the path is not a work tree.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from coador.redact import sanitize_snippet

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


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


def _run_git(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
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
    commit = _run_git(repo_root, "rev-parse", "HEAD")
    if commit is None:
        return UNAVAILABLE

    toplevel = _run_git(repo_root, "rev-parse", "--show-toplevel")
    status = _run_git(repo_root, "status", "--porcelain", "--", str(repo_root))
    return GitInfo(
        commit=commit.strip(),
        dirty=None if status is None else bool(status.strip()),
        root=sanitize_snippet(toplevel.strip()) if toplevel else None,
    )


def changed_files_since(repo_root: Path, commit: str) -> int | None:
    """Count files under ``repo_root`` that differ between ``commit`` and the work tree."""
    output = _run_git(repo_root, "diff", "--name-only", commit, "--", str(repo_root))
    if output is None:
        return None
    return len([line for line in output.splitlines() if line.strip()])
