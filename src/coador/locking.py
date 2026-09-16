"""Small cross-process lock used to serialize knowledge-base publication."""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, BinaryIO

from coador.paths import checked_path


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold an advisory exclusive lock until the context exits.

    The file is intentionally retained: deleting a live lock file permits a new
    process to lock a different inode and defeats serialization.
    """
    checked_path(path.parent, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "r+b", buffering=0) as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\n")
        _acquire(handle)
        try:
            yield
        finally:
            _release(handle)


def _acquire(handle: BinaryIO) -> None:
    if os.name == "nt":
        _acquire_windows(handle, import_module("msvcrt"))
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _acquire_windows(handle: BinaryIO, msvcrt: Any) -> None:
    """Wait for a Windows byte lock without msvcrt's ten-retry limit."""
    retry_errors = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
    retry_winerrors = {32, 33}  # sharing violation, lock violation
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if (
                exc.errno not in retry_errors
                and getattr(exc, "winerror", None) not in retry_winerrors
            ):
                raise
            time.sleep(0.05)
        else:
            return


def _release(handle: BinaryIO) -> None:
    if os.name == "nt":
        msvcrt = import_module("msvcrt")

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
