"""Public API of region growing and automatic segmentation.

Not implemented yet. Methods and measurements:
`.work/research/algorithms-mesh.md` 2.3-2.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.primitives import PrimitiveKind

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.session.jobs import JobContext

type GrowMode = Literal["primitive", "smooth", "normal"]


@dataclass(frozen=True)
class GrownRegion:
    """Faces of the grown region and the primitive that explains them (if any)."""

    faces: npt.NDArray[np.int64]
    kind: PrimitiveKind | None
    rms: float | None


@dataclass(frozen=True)
class Segmentation:
    """One label per face (0 = unassigned) plus type and RMS per label."""

    labels: npt.NDArray[np.uint16]
    kinds: list[PrimitiveKind | None]
    rms: list[float | None]


def grow_region(
    mesh: EvalMesh,
    seed_face: int,
    mode: GrowMode,
    tolerance: float,
    kind: PrimitiveKind | None = None,
) -> GrownRegion:
    """Grow a region of one surface from a seed face (smart select)."""
    raise NotImplementedError("region growing")


def segment(mesh: EvalMesh, sensitivity: float, min_area: float, job: JobContext) -> Segmentation:
    """Split the scan into regions of single primitives (runs on a cached 200 k-face copy)."""
    raise NotImplementedError("automatic segmentation")
