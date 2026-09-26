"""Public API of section sketches.

Not implemented yet. Pipeline: section in an explicit plane frame, noise and
tolerance from the raw section points, dynamic-programming split into lines and
arcs, constraint inference, joint least-squares refit, exact junctions, value
snapping. Methods and measurements: `.work/research/algorithms-cad.md` section 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from m2c_kernel.document.results import PlaneFrame

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.features.types.sketch import SketchParams


@dataclass(frozen=True)
class SectionPoints:
    """Section polylines in plane coordinates (u, v) and the estimated noise."""

    closed_loops: list[npt.NDArray[np.float64]]
    open_chains: list[npt.NDArray[np.float64]]
    noise: float


def section_points(mesh: EvalMesh, frame: PlaneFrame, offset: float) -> SectionPoints:
    """Intersect the scan with the plane `offset` millimetres from the sketch plane."""
    raise NotImplementedError("scan sections")


def auto_fit(section: SectionPoints, tolerance: float | None) -> SketchParams:
    """Fit lines, arcs and circles with constraints to a section."""
    raise NotImplementedError("automatic sketch fitting")


def profile_faces(params: SketchParams, frame: PlaneFrame) -> tuple[list[Any], list[str]]:
    """Planar `TopoDS_Face` objects of the closed loops and their loop ids."""
    raise NotImplementedError("sketch profiles")
