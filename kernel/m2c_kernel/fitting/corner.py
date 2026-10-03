"""The radius of a rounded edge, measured from the scan in cross-sections.

Seen in a cross-section, a rounded edge is a corner of two straight faces joined by an
arc tangent to both: line, arc, line. The modelled faces fix the sharp corner and the
directions of both faces away from it (`CornerFrame`); the scan points in a thin slab
across the edge then decide the one free value, the radius.

Each cross-section is fitted on its own: a search over the radius of the capped
squared distance (points of other faces nearby count only up to the cap), then once
more inside a window of max(2.5 r, 1 mm) around the corner, where only the corner is.
The edge's radius is the median over the sections; where something interrupts the
rounding (a button cut into it), single sections read too small or too large.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from m2c_kernel.fitting.corner_profile import Corner
from m2c_kernel.geometry import FloatArray, unit

SLAB_MM = 0.25
"""Half width of the slab of scan points across the edge."""
REACH_MM = 5.0
"""The first fit uses the points this far from the corner."""
WINDOW_FACTOR = 2.5
MIN_WINDOW_MM = 1.0
CAP_NOISE = 4.0
MIN_CAP_MM = 0.08
"""Points farther from the profile than max(CAP_NOISE x noise, MIN_CAP_MM) count as that."""
MIN_POINTS = 8
MIN_SIDE_POINTS = 2
"""A section measures only with scan points on both faces beyond the rounding."""
MAX_OPENING_DEG = 170.0
"""Faces meeting flatter than this are no edge to round."""
RADIUS_STEPS = 48
MAX_OFFSET_MM = 0.3
"""The scan's faces may lie this far from the modelled ones (a flat top on a slight dome)."""
OFFSET_STEPS = 49
OFFSET_ROUNDS = 2
MAX_FIRST_POINTS = 600
SHARP_MM = 0.05
"""Radii below this are a sharp edge (0)."""


@dataclass(frozen=True)
class CornerFrame:
    """Where a cross-section crosses an edge of the model.

    Attributes:
        point: The sharp corner the two faces meet in (3,).
        tangent: Unit direction of the edge (3,).
        faces: Unit directions along both faces away from the edge, perpendicular to
            the tangent.
    """

    point: FloatArray
    tangent: FloatArray
    faces: tuple[FloatArray, FloatArray]


@dataclass(frozen=True)
class SectionFit:
    radius: float
    """0 for a sharp edge."""
    rms: float
    """RMS distance of the points inside the window to the fitted corner."""
    points: int
    corner: tuple[float, float] = (0.0, 0.0)
    """Where the scan's faces meet in the section's (face 1, across) frame (mm)."""


@dataclass(frozen=True)
class EdgeRadius:
    """The radius of a rounded edge over all its sections."""

    radius: float
    """Median of the sections' radii (mm), 0 for a sharp edge."""
    uncertainty: float
    """Standard uncertainty of the median (mm)."""
    rms: float
    """RMS distance of the scan points to the sections' corners at their own radius."""
    samples: int
    """Sections that measured the rounding."""
    spread: tuple[float, float]
    """10th and 90th percentile of the sections' radii."""


def edge_radius(
    vertices: FloatArray,
    tree: cKDTree,
    frames: Sequence[CornerFrame],
    noise: float,
    *,
    max_radius: float | None = None,
) -> EdgeRadius | None:
    """The radius of the edge through `frames`; None when too few sections measured it.

    Args:
        vertices: Scan points, (n, 3), in the frames' coordinates.
        tree: KD-tree of `vertices`.
        frames: Cross-sections along the edge.
        noise: Scan noise (mm); sets the cap of the distances.
        max_radius: Largest radius to consider (for example below half a button's width).
    """
    if not frames:
        return None
    cap = max(CAP_NOISE * noise, MIN_CAP_MM)
    centres = np.array([frame.point for frame in frames])
    nearby = tree.query_ball_point(centres, REACH_MM, workers=-1)
    fits = [
        fit
        for frame, indices in zip(frames, nearby, strict=True)
        if (fit := section_radius(vertices[indices], frame, cap, max_radius)) is not None
    ]
    if not fits or len(fits) < max(3, len(frames) // 4):
        return None
    radii = np.array([fit.radius for fit in fits])
    median = float(np.median(radii))
    mad = 1.4826 * float(np.median(np.abs(radii - median)))
    squares = sum(fit.rms**2 * fit.points for fit in fits)
    count = sum(fit.points for fit in fits)
    p10, p90 = (float(value) for value in np.percentile(radii, [10.0, 90.0]))
    return EdgeRadius(
        radius=median if median >= SHARP_MM else 0.0,
        uncertainty=1.2533 * mad / np.sqrt(len(fits)),
        rms=float(np.sqrt(squares / max(count, 1))),
        samples=len(fits),
        spread=(p10, p90),
    )


def section_radius(
    near: FloatArray,
    frame: CornerFrame,
    cap: float,
    max_radius: float | None = None,
) -> SectionFit | None:
    """The radius of the corner in one cross-section, or None without enough points.

    `near` are the scan points within `REACH_MM` of the corner.
    """
    e1, e2 = section_axes(frame)
    opening = float(np.arccos(np.clip(e1 @ e2, -1.0, 1.0)))
    if not np.radians(5.0) < opening < np.radians(MAX_OPENING_DEG):
        return None
    nearby = near - frame.point
    slab = np.abs(nearby @ frame.tangent) < SLAB_MM
    if int(slab.sum()) < MIN_POINTS:
        return None
    w = np.cross(frame.tangent, e1)
    points = np.column_stack([nearby[slab] @ e1, nearby[slab] @ w])
    wide = Corner(np.array([1.0, 0.0]), unit(np.array([e2 @ e1, e2 @ w])), REACH_MM)
    # The tangent length stays inside the reach.
    largest = 0.9 * REACH_MM * float(np.tan(wide.half))
    if max_radius is not None:
        largest = min(largest, max_radius)
    # Dense scans give thousands of points: an even subset decides the first fit.
    first = points[:: max(1, len(points) // MAX_FIRST_POINTS)]
    origin = np.zeros((1, 2))
    radius = _best_radius(wide, first, origin, cap, largest)
    window = max(WINDOW_FACTOR * wide.tangent_length(radius), MIN_WINDOW_MM)
    inner = points[np.linalg.norm(points, axis=1) < window]
    if len(inner) < MIN_POINTS:
        return None
    corner = Corner(wide.d1, wide.d2, window)
    largest = min(largest, 0.9 * window * float(np.tan(corner.half)))
    offsets = _face_offsets(corner, inner, window)
    for _ in range(OFFSET_ROUNDS):
        radius = _best_radius(corner, inner, corner.shifted(offsets), cap, largest)
        for face in (0, 1):
            offsets[face] = _best_offset(corner, inner, offsets, face, radius, cap)
    at = corner.shifted(offsets)
    radius = _best_radius(corner, inner, at, cap, largest)
    distance = corner.distances(inner, at, np.array([radius]))[0]
    inliers = distance < cap
    local = inner[inliers] - at[0]
    beyond = corner.tangent_length(radius) + 0.1 * window
    if min(int((local @ d > beyond).sum()) for d in (corner.d1, corner.d2)) < MIN_SIDE_POINTS:
        return None
    if int(inliers.sum()) < MIN_POINTS:
        return None
    return SectionFit(
        radius=float(radius),
        rms=float(np.sqrt(np.mean(distance[inliers] ** 2))),
        points=int(inliers.sum()),
        corner=(float(at[0, 0]), float(at[0, 1])),
    )


def section_axes(frame: CornerFrame) -> tuple[FloatArray, FloatArray]:
    """Both face directions with any part along the tangent removed (unit)."""
    t = frame.tangent
    e1, e2 = (unit(face - (face @ t) * t) for face in frame.faces)
    return e1, e2


def _best_radius(
    corner: Corner, points: FloatArray, at: FloatArray, cap: float, largest: float
) -> float:
    """The radius of least capped squared distance: a grid, then a finer grid around it."""
    if largest <= 0.0:
        return 0.0
    radii = np.linspace(0.0, largest, RADIUS_STEPS)
    cost = corner.costs(points, np.repeat(at, len(radii), axis=0), radii, cap)
    best = int(np.argmin(cost))
    step = radii[1] - radii[0]
    fine = np.linspace(max(radii[best] - step, 0.0), min(radii[best] + step, largest), 25)
    cost = corner.costs(points, np.repeat(at, len(fine), axis=0), fine, cap)
    return float(fine[int(np.argmin(cost))])


def _face_offsets(corner: Corner, points: FloatArray, window: float) -> FloatArray:
    """Where the scan's faces lie across the modelled ones, from the points beyond the
    rounding (the outer half of the window along each face); 0 without such points."""
    offsets = np.zeros(2)
    for face, direction in enumerate((corner.d1, corner.d2)):
        normal = np.array([-direction[1], direction[0]])
        along, across = points @ direction, points @ normal
        far = (along > window / 2.0) & (np.abs(across) < MAX_OFFSET_MM)
        if int(far.sum()) >= MIN_SIDE_POINTS:
            offsets[face] = float(np.median(across[far]))
    return offsets


def _best_offset(
    corner: Corner, points: FloatArray, offsets: FloatArray, face: int, radius: float, cap: float
) -> float:
    """The offset of one face (the other kept) of least capped squared distance."""
    candidates = np.repeat(offsets[None, :], OFFSET_STEPS, axis=0)
    candidates[:, face] = np.linspace(-MAX_OFFSET_MM, MAX_OFFSET_MM, OFFSET_STEPS)
    radii = np.full(OFFSET_STEPS, radius)
    cost = corner.costs(points, corner.shifted(candidates), radii, cap)
    return float(candidates[int(np.argmin(cost)), face])
