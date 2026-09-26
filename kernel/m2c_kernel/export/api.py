"""Public API of STEP and STL export.

Not implemented yet. STEP is written with XCAF (exact product names), unit
millimetre and an explicit schema, to a temporary file that is read back and
compared (valid, solid count, volume) before it replaces the target.
Measurements: `.work/research/algorithms-cad.md` section 5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from m2c_kernel.document.results import Body


def write_step(
    path: Path, bodies: dict[str, Body], names: dict[str, str], schema: Literal["AP214", "AP242"]
) -> None:
    """Write bodies to STEP and verify the file by reading it back."""
    raise NotImplementedError("STEP export")


def write_stl(path: Path, bodies: dict[str, Body], deflection: float) -> None:
    """Write the tessellated bodies to a binary STL."""
    raise NotImplementedError("STL export")
