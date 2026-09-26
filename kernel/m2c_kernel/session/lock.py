"""The lock that marks a session directory as owned by a running kernel.

The operating system releases the lock when the process ends, also after a
crash, so a session directory whose lock can be taken belongs to nobody and
can be offered for recovery.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import BinaryIO

LOCK_FILE = "session.lock"
INFO_FILE = "session.json"


class SessionBusyError(RuntimeError):
    """Another running kernel owns the session directory."""


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class SessionLock:
    def __init__(self, handle: BinaryIO) -> None:
        self._handle: BinaryIO | None = handle

    @classmethod
    def acquire(cls, directory: Path) -> SessionLock:
        handle = (directory / LOCK_FILE).open("a+b")
        if not _try_lock(handle):
            handle.close()
            raise SessionBusyError(str(directory))
        info = {"pid": os.getpid(), "started": time.time()}
        (directory / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")
        return cls(handle)

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        finally:
            self._handle.close()
            self._handle = None


def is_owned(directory: Path) -> bool:
    """True while a running kernel holds the session lock."""
    path = directory / LOCK_FILE
    if not path.exists():
        return False
    with path.open("a+b") as handle:
        if not _try_lock(handle):
            return True
        _unlock(handle)
        return False
