from __future__ import annotations

import errno
import multiprocessing
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import coador.locking as locking_module
from coador.locking import exclusive_file_lock


def _hold_lock(path: str, acquired: Any, release: Any) -> None:
    with exclusive_file_lock(Path(path)):
        acquired.set()
        release.wait(10)


def _wait_for_lock(path: str, acquired: Any) -> None:
    with exclusive_file_lock(Path(path)):
        acquired.set()


def test_lock_serializes_separate_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    holder_acquired = context.Event()
    waiter_acquired = context.Event()
    release = context.Event()
    path = str(tmp_path / "refresh.lock")
    holder = context.Process(target=_hold_lock, args=(path, holder_acquired, release))
    waiter = context.Process(target=_wait_for_lock, args=(path, waiter_acquired))
    try:
        holder.start()
        assert holder_acquired.wait(5)
        waiter.start()
        assert not waiter_acquired.wait(0.2)
        release.set()
        assert waiter_acquired.wait(5)
        holder.join(5)
        waiter.join(5)
        assert holder.exitcode == waiter.exitcode == 0
        assert Path(path).read_bytes() == b"\n"
    finally:
        release.set()
        for process in (holder, waiter):
            if process.is_alive():
                process.terminate()
            process.join(5)


def test_windows_lock_retries_past_msvcrt_builtin_limit(monkeypatch) -> None:
    attempts = 0

    def locking(_descriptor: int, _mode: int, _length: int) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 12:
            raise OSError(errno.EACCES, "locked")

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, locking=locking)
    monkeypatch.setattr(locking_module.time, "sleep", lambda _delay: None)
    with tempfile.TemporaryFile("w+b") as handle:
        locking_module._acquire_windows(handle, fake_msvcrt)

    assert attempts == 13
