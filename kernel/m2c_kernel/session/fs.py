"""File operations that tolerate the short-lived locks Windows puts on files.

Virus scanners and indexers open new files for a moment, and a file that is
still open cannot be replaced or deleted on Windows. These helpers retry for a
short time instead of failing the whole operation.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

_ATTEMPTS = 10
_DELAY_S = 0.05


def replace_with_retry(source: Path, target: Path) -> None:
    """`os.replace` that retries while the target is locked by another process."""
    for attempt in range(_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(_DELAY_S * (attempt + 1))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write a file so that readers see either the old or the complete new content."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        replace_with_retry(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def remove_quietly(path: Path) -> bool:
    """Delete a file; returns False if it is still locked (the caller may retry later)."""
    for attempt in range(3):
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            time.sleep(_DELAY_S * (attempt + 1))
    return False
