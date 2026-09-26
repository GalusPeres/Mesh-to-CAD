"""Public API of region growing and automatic segmentation.

Methods and measurements: `.work/research/algorithms-mesh.md` 2.3-2.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.api import FitError, PrimitiveKind
from m2c_kernel.segmentation.analysis import analyse
from m2c_kernel.segmentation.auto import Tuning, segment_mesh
from m2c_kernel.segmentation.grow import (
    START_RADIUS_MM,
    WIDE_START_RADIUS_MM,
    auto_kinds,
    fit_faces,
    grow_normal,
    grow_primitive,
    grow_smooth,
    start_patch,
)

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.session.jobs import JobContext

type GrowMode = Literal["primitive", "smooth", "normal"]

DEFAULT_MAX_ANGLE_DEG = 10.0


@dataclass(frozen=True)
class GrownRegion:
    """Faces of the grown region and the primitive that explains them (if any)."""

    faces: npt.NDArray[np.int64]
    kind: PrimitiveKind | None
    rms: float | None


@dataclass(frozen=True)
class Segmentation:
    """One label per face (0 = unassigned) plus type and RMS per label (index = label - 1)."""

    labels: npt.NDArray[np.uint16]
    kinds: list[PrimitiveKind | None]
    rms: list[float | None]


def default_tolerance(mesh: EvalMesh) -> float:
    """Distance tolerance of a fit-filter-connect growth: 4 x the scan noise."""
    return 4.0 * analyse(mesh).noise


def grow_region(
    mesh: EvalMesh,
    seed_face: int,
    mode: GrowMode,
    tolerance: float | None,
    rng: np.random.Generator,
    kind: PrimitiveKind | None = None,
    max_angle_deg: float = DEFAULT_MAX_ANGLE_DEG,
) -> GrownRegion:
    """Grow a region of one surface from a seed face (smart select).

    `tolerance` is the distance limit of the primitive mode (None: 4 x noise); the
    other modes use only `max_angle_deg`. A synthetic seed face grows nothing.
    """
    analysis = analyse(mesh)
    if not analysis.usable[seed_face]:
        return GrownRegion(np.zeros(0, dtype=np.int64), None, None)
    if mode == "smooth":
        return GrownRegion(
            np.nonzero(grow_smooth(analysis, seed_face, max_angle_deg))[0], None, None
        )
    if mode == "normal":
        return GrownRegion(
            np.nonzero(grow_normal(analysis, seed_face, max_angle_deg))[0], None, None
        )
    limit = tolerance if tolerance is not None and tolerance > 0 else default_tolerance(mesh)
    radius = WIDE_START_RADIUS_MM if kind in ("cone", "torus") else START_RADIUS_MM
    patch = start_patch(analysis, seed_face, radius)
    try:
        chosen = kind or fit_faces(analysis, patch, None, rng, auto_kinds(analysis, patch)).kind
    except FitError:
        return GrownRegion(np.nonzero(patch)[0], None, None)
    grown = grow_primitive(
        analysis, seed_face, patch, chosen, limit, max_angle_deg, rng, relaxed=analysis.crease
    )
    if grown.fit is None:
        return GrownRegion(np.nonzero(grown.region)[0], None, None)
    return GrownRegion(np.nonzero(grown.region)[0], grown.fit.kind, grown.fit.rms)


def segment(
    mesh: EvalMesh,
    sensitivity: float,
    min_area: float,
    job: JobContext,
    rng: np.random.Generator,
    faces: npt.NDArray[np.int64] | None = None,
) -> Segmentation:
    """Split the scan (or only `faces`) into regions of single primitives.

    Runs on a cached 200 k-face copy; labels are transferred by nearest centroid.
    Reports progress per accepted region and checks for cancellation often.
    """
    within = None
    if faces is not None:
        within = np.zeros(len(mesh.faces), dtype=bool)
        within[faces] = True
    result = segment_mesh(mesh, Tuning.from_sensitivity(sensitivity, min_area), job, rng, within)
    labels = np.where(result.labels >= 0, result.labels + 1, 0).astype(np.uint16)
    return Segmentation(
        labels=labels,
        kinds=[fit.kind for fit in result.fits],
        rms=[fit.rms for fit in result.fits],
    )
