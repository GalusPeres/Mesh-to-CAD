"""Tests against the PyInstaller build named by `M2C_KERNEL_EXE` (the packaging gate).

They catch what the development tests cannot see: modules, data files and DLLs
that the frozen build left out, and the multiprocessing start of a frozen child.
Without `M2C_KERNEL_EXE` they are skipped.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.kernel_process import KernelProcess

FROZEN_EXE = os.environ.get("M2C_KERNEL_EXE")

requires_frozen_kernel = pytest.mark.skipif(
    not FROZEN_EXE, reason="set M2C_KERNEL_EXE to the built m2c-kernel.exe"
)


@pytest.fixture
def frozen(tmp_path: Path) -> Iterator[KernelProcess]:
    """A frozen kernel that has finished loading its libraries."""
    assert FROZEN_EXE and Path(FROZEN_EXE).is_file(), f"not a file: {FROZEN_EXE}"
    process = KernelProcess(tmp_path / "session")
    process.next_event("ready", timeout=60)
    assert process.call("system.info").ok
    yield process
    process.stop()
