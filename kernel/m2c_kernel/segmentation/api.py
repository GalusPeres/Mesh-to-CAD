"""Public API of region growing, automatic segmentation and region labels.

Methods and measurements: `.work/research/algorithms-mesh.md` 2.3-2.6.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.api import FitError, PrimitiveKind, fit_best
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.segmentation.analysis import analyse, is_analysed
from m2c_kernel.segmentation.auto import Tuning, segment_mesh
from m2c_kernel.segmentation.grow import (
    START_RADIUS_MM,
    WIDE_START_RADIUS_MM,
    auto_kinds,
    fit_faces,
    grow_normal,
    grow_primitive,
    grow_smooth,
    region_points,
    simplest_fit,
    start_patch,
)
from m2c_kernel.segmentation.labels import (
    PALETTE_SIZE,
    adjacency,
    assign_colors,
    free_labels,
    label_sizes,
    match_regions,
)
from m2c_kernel.segmentation.lod import LEVELS_OF_DETAIL, LevelOfDetailCache

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.session.jobs import JobContext

__all__ = [
    "DEFAULT_MAX_ANGLE_DEG",
    "LEVELS_OF_DETAIL",
    "PALETTE_SIZE",
    "GrowMode",
    "GrownRegion",
    "LevelOfDetailCache",
    "Segmentation",
    "adjacency",
    "assign_colors",
    "classify_faces",
    "default_tolerance",
    "free_labels",
    "grow_region",
    "is_prepared",
    "label_sizes",
    "match_regions",
    "prepare",
    "segment",
]

type GrowMode = Literal["primitive", "smooth", "normal"]

DEFAULT_MAX_ANGLE_DEG = 10.0
"""Jet normals are accurate to 1-3 degrees; with 20 degrees planes creep into fillets."""
TOLERANCE_FACTOR = 4.0
COLLAPSED_SHARE = 0.5
"""A growth that keeps fewer faces than this share of its start patch has failed."""
CLASSIFY_ACCEPT = 2.0
"""A face set counts as one primitive when its robust sigma is below this x the noise."""


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
    kinds: list[PrimitiveKind]
    rms: list[float]


def is_prepared(mesh: EvalMesh) -> bool:
    """True when region growing on `mesh` needs no analysis first (no progress bar needed)."""
    return is_analysed(mesh)


def prepare(mesh: EvalMesh, check: Callable[[], None]) -> None:
    """Compute the per-mesh data of region growing (jet normals, curvature, crease zone)."""
    analyse(mesh).warm_up(check)


def default_tolerance(mesh: EvalMesh) -> float:
    """Distance tolerance of a fit-filter-connect growth: 4 x the scan noise."""
    return TOLERANCE_FACTOR * analyse(mesh).noise


def grow_region(
    mesh: EvalMesh,
    seed_face: int,
    mode: GrowMode,
    rng: np.random.Generator,
    *,
    kind: PrimitiveKind | None = None,
    tolerance: float | None = None,
    max_angle_deg: float = DEFAULT_MAX_ANGLE_DEG,
    check: Callable[[], None] | None = None,
) -> GrownRegion:
    """Grow a region of one surface from a seed face (smart select).

    `tolerance` is the distance limit of the primitive mode (None: 4 x noise); all
    modes use `max_angle_deg`. `kind` None chooses the primitive type from the
    start patch and reports the simplest type that explains the grown region. A
    synthetic seed face grows nothing.
    """
    analysis = analyse(mesh)
    if not analysis.usable[seed_face]:
        return GrownRegion(np.zeros(0, dtype=np.int64), None, None)
    if mode == "smooth":
        region = grow_smooth(analysis, seed_face, max_angle_deg)
        return GrownRegion(np.nonzero(region)[0], None, None)
    if mode == "normal":
        region = grow_normal(analysis, seed_face, max_angle_deg)
        return GrownRegion(np.nonzero(region)[0], None, None)

    limit = tolerance if tolerance is not None and tolerance > 0 else default_tolerance(mesh)
    radius = WIDE_START_RADIUS_MM if kind in ("cone", "torus") else START_RADIUS_MM
    patch = start_patch(analysis, seed_face, radius)
    try:
        chosen = kind or fit_faces(analysis, patch, None, rng, auto_kinds(analysis, patch)).kind
    except FitError:
        return GrownRegion(np.nonzero(patch)[0], None, None)
    grown = grow_primitive(
        analysis,
        seed_face,
        patch,
        chosen,
        limit,
        max_angle_deg,
        rng,
        relaxed=analysis.crease,
        check=check,
    )
    faces = np.nonzero(grown.region)[0]
    if grown.fit is None or len(faces) < COLLAPSED_SHARE * int(patch.sum()):
        # the primitive did not explain its own start patch (a seed on a narrow
        # band or right at a tangent edge): offer the patch without a type
        return GrownRegion(np.nonzero(patch)[0], None, None)
    fit = grown.fit if kind is not None else simplest_fit(analysis, grown.region, grown.fit, rng)
    return GrownRegion(faces, fit.kind, fit.rms)


def classify_faces(
    mesh: EvalMesh, faces: npt.NDArray[np.int64], rng: np.random.Generator
) -> tuple[PrimitiveKind | None, float | None]:
    """The primitive type and RMS of a face set, or (None, None) if no primitive explains it.

    Synthetic faces are ignored; fewer than `MIN_FIT_FACES` usable faces are not
    classified.
    """
    analysis = analyse(mesh)
    usable = faces[analysis.usable[faces]]
    if len(usable) < MIN_FIT_FACES:
        return None, None
    points, normals = region_points(analysis, usable, rng)
    try:
        fit = fit_best(points, normals, rng, noise=analysis.noise)[0]
    except FitError:
        return None, None
    if fit.sigma > CLASSIFY_ACCEPT * analysis.noise:
        return None, None
    return fit.kind, fit.rms


def segment(
    mesh: EvalMesh,
    lod: EvalMesh,
    sensitivity: float,
    min_area: float,
    job: JobContext,
    rng: np.random.Generator,
    faces: npt.NDArray[np.int64] | None = None,
) -> Segmentation:
    """Split the scan (or only `faces`) into regions of single primitives.

    `lod` is the reduced copy from `LEVELS_OF_DETAIL` (or `mesh` itself); labels
    are transferred by nearest centroid. Reports progress per accepted region and
    checks for cancellation at least every 200 ms.
    """
    within = None
    if faces is not None:
        within = np.zeros(len(mesh.faces), dtype=bool)
        within[faces] = True
    result = segment_mesh(
        mesh, lod, Tuning.from_sensitivity(sensitivity, min_area), job, rng, within
    )
    labels = np.where(result.labels >= 0, result.labels + 1, 0).astype(np.uint16)
    return Segmentation(labels=labels, kinds=[fit.kind for fit in result.fits], rms=result.rms)
