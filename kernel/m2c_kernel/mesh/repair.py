"""Mesh preparation: repair, small parts, hole filling, reduction, smoothing.

Not implemented yet. Every operation returns the new mesh, an exact face index
map `new_to_old` (see `m2c_kernel.mesh.remap`) and counts for the report.
Methods and measurements: `.work/research/algorithms-mesh.md` 1.2-1.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.load import RawMesh


@dataclass(frozen=True)
class MeshChange:
    """Result of a preparation step.

    Attributes:
        mesh: The new mesh.
        new_to_old: Source face of every new face, -1 for faces without a source.
        synthetic: True for faces created by the step (hole filling).
        counts: Numbers for the report, keyed by i18n-friendly names.
    """

    mesh: RawMesh
    new_to_old: npt.NDArray[np.int64]
    synthetic: npt.NDArray[np.bool_]
    counts: dict[str, int] = field(default_factory=dict)


def repair(mesh: RawMesh) -> MeshChange:
    """Weld, drop degenerate and duplicate faces, fix winding, orient outward."""
    raise NotImplementedError("mesh repair")


def remove_small_parts(mesh: RawMesh, min_ratio: float, min_faces: int) -> MeshChange:
    """Remove connected components smaller than `min_ratio` of the largest one."""
    raise NotImplementedError("removing small parts")


def fill_holes(mesh: RawMesh, max_perimeter: float) -> MeshChange:
    """Close holes up to `max_perimeter` millimetres; larger holes stay open."""
    raise NotImplementedError("hole filling")


def decimate(mesh: RawMesh, target_faces: int) -> MeshChange:
    """Reduce to `target_faces` in a separate process (fast_simplification is not thread-safe)."""
    raise NotImplementedError("reduction")


def smooth_for_display(mesh: RawMesh, iterations: int) -> npt.NDArray[np.float64]:
    """Taubin-smoothed vertex positions for display and scan export; never used for fitting."""
    raise NotImplementedError("display smoothing")
