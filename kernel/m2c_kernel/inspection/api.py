"""Public API of the deviation analysis and measurements.

Sign convention: a positive distance means the scan point lies outside the body
(excess material on the real part), negative means inside.

Deviation: seeded vertex-ring descent with per-face walkers, B-Rep edge seeds and
pseudo-normal signs on a reference tessellation with linear deflection at most
tolerance / 20 (`distance.py`, `reference.py`). Measured on the test block: identical
to brute force within 5e-5 mm, signs identical to `BRepClass3d_SolidClassifier` for
every point farther than the deflection, about 6 s per million points (1M-point test).
Measurements: closed form between primitives (`measure.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.inspection import ProgressStage
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray
from m2c_kernel.inspection.distance import closest_points
from m2c_kernel.inspection.measure import (
    DistanceKind,
    FitCovariance,
    Geometry,
    GeometryKind,
    Item,
    Measurement,
    OriginItem,
    fit_covariance,
    geometry_of_construction,
    geometry_of_face,
    geometry_of_origin,
    geometry_of_primitive,
    measure_items,
)
from m2c_kernel.inspection.reference import ReferenceCache, ReferenceSurface, reference_deflection
from m2c_kernel.inspection.stats import (
    DeviationStats,
    FaceDeviation,
    deviation_stats,
    per_face_stats,
)

if TYPE_CHECKING:
    from m2c_kernel.session.jobs import JobContext

__all__ = [
    "PREVIEW_POINTS",
    "BodyInput",
    "DeviationMap",
    "DeviationStats",
    "DistanceKind",
    "FaceDeviation",
    "FitCovariance",
    "Geometry",
    "GeometryKind",
    "Item",
    "Measurement",
    "OriginItem",
    "ReferenceSurface",
    "SignedDistances",
    "deviation_map",
    "deviation_stats",
    "deviation_summary",
    "fit_covariance",
    "geometry_of_construction",
    "geometry_of_face",
    "geometry_of_origin",
    "geometry_of_primitive",
    "measure_items",
    "reference_for",
    "signed_distances",
]

PREVIEW_POINTS = 50_000
"""Scan points used for the deviation summary of a tool preview (ARCHITECTURE.md 4.7)."""

_REFERENCES = ReferenceCache()


@dataclass(frozen=True)
class BodyInput:
    """A body to compare with; `key` changes whenever its geometry changes (cache key)."""

    body_id: str
    key: str
    body: Body


@dataclass(frozen=True)
class SignedDistances:
    """Distance per point (NaN beyond the search distance) and the global B-Rep face hit.

    `face_ids` index the reference's faces (-1 without a result);
    `ReferenceSurface.body_face` turns them into (body id, face index).
    """

    distances: npt.NDArray[np.float32]
    face_ids: npt.NDArray[np.int32]


@dataclass(frozen=True)
class DeviationMap:
    """Signed distance per scan vertex and per scan face (mean of its vertices), NaN = none."""

    values: npt.NDArray[np.float32]
    face_values: npt.NDArray[np.float32]
    stats: DeviationStats
    faces: list[FaceDeviation]


def reference_for(
    bodies: Sequence[BodyInput], tolerance: float, job: JobContext | None = None
) -> ReferenceSurface:
    """The reference surface of the bodies, cached by their keys and the deflection."""
    deflection = reference_deflection(tolerance)
    keys = [body.key for body in bodies]
    pairs = [(body.body_id, body.body) for body in bodies]
    if job is None:
        return _REFERENCES.get(keys, pairs, deflection)
    with job.native(ProgressStage.PREPARING):
        return _REFERENCES.get(keys, pairs, deflection)


def signed_distances(
    points: FloatArray,
    reference: ReferenceSurface,
    max_distance: float,
    job: JobContext | None = None,
) -> SignedDistances:
    """Signed distances to the reference; points farther than `max_distance` get NaN."""
    points = np.asarray(points, dtype=np.float64)
    distances = np.full(len(points), np.nan, dtype=np.float32)
    face_ids = np.full(len(points), -1, dtype=np.int32)
    if len(points) == 0:
        return SignedDistances(distances, face_ids)
    # The surface lies within one edge length of its nearest vertex, so points whose nearest
    # reference vertex is farther than max_distance + that length cannot have a result.
    vertex_distance, _ = reference.vertex_tree.query(points, k=1, workers=-1)
    candidates = np.flatnonzero(vertex_distance <= max_distance + reference.max_edge)
    if len(candidates) == 0:
        return SignedDistances(distances, face_ids)
    closest = closest_points(reference, points[candidates], job)
    inside = np.abs(closest.signed) <= max_distance
    rows = candidates[inside]
    distances[rows] = closest.signed[inside].astype(np.float32)
    face_ids[rows] = reference.face_id[closest.triangle[inside]].astype(np.int32)
    return SignedDistances(distances, face_ids)


def deviation_map(
    vertices: FloatArray,
    faces: npt.NDArray[np.int64],
    synthetic: npt.NDArray[np.bool_],
    bodies: Sequence[BodyInput],
    tolerance: float,
    max_distance: float,
    job: JobContext,
) -> DeviationMap:
    """Deviation of every scan vertex from the bodies (vertices in part coordinates).

    Vertices used only by synthetic triangles (filled holes) are not measured data and
    get no value.
    """
    reference = reference_for(bodies, tolerance, job)
    measured = np.zeros(len(vertices), dtype=bool)
    measured[faces[~synthetic].ravel()] = True
    rows = np.flatnonzero(measured)
    result = signed_distances(vertices[rows], reference, max_distance, job)
    values = np.full(len(vertices), np.nan, dtype=np.float32)
    values[rows] = result.distances
    face_ids = np.full(len(vertices), -1, dtype=np.int32)
    face_ids[rows] = result.face_ids
    return DeviationMap(
        values=values,
        face_values=_face_means(values, faces),
        stats=deviation_stats(values, tolerance),
        faces=per_face_stats(values, face_ids, tolerance, reference.body_face),
    )


def deviation_summary(
    vertices: FloatArray,
    bodies: Sequence[BodyInput],
    tolerance: float,
    max_distance: float,
    rng: np.random.Generator,
    job: JobContext | None = None,
) -> tuple[DeviationStats, int]:
    """Statistics of the scan points near the bodies, on at most `PREVIEW_POINTS` of them.

    Returns the statistics and the number of points compared.
    """
    reference = reference_for(bodies, tolerance, job)
    low, high = reference.bounds[0] - max_distance, reference.bounds[1] + max_distance
    near = np.flatnonzero(np.all((vertices >= low) & (vertices <= high), axis=1))
    if len(near) > PREVIEW_POINTS:
        near = np.sort(rng.choice(near, PREVIEW_POINTS, replace=False))
    result = signed_distances(vertices[near], reference, max_distance, job)
    return deviation_stats(result.distances, tolerance), len(near)


def _face_means(
    values: npt.NDArray[np.float32], faces: npt.NDArray[np.int64]
) -> npt.NDArray[np.float32]:
    corner = values[faces].astype(np.float64)
    finite = np.isfinite(corner)
    count = finite.sum(axis=1)
    total = np.where(finite, corner, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    return means.astype(np.float32)
