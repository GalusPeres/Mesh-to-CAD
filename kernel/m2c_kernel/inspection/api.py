"""Public API of the deviation analysis.

Sign convention: a positive distance means the scan point lies outside the
body (excess material on the real part), negative means inside.

Method: seeded vertex-ring descent with per-face walkers, B-Rep edge seeds and
pseudo-normal signs on a reference tessellation with linear deflection at most
tolerance / 20 (`inspection/distance.py`, `inspection/reference.py`).
Measurements: `.work/research/algorithms-cad.md` section 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.inspection import ProgressStage
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray
from m2c_kernel.inspection.distance import closest_points
from m2c_kernel.inspection.reference import (
    ReferenceSurface,
    build_reference,
    reference_deflection,
)

if TYPE_CHECKING:
    from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class SignedDistances:
    """Distance per point (NaN beyond the search distance) and the B-Rep face hit.

    `face_ids` are global face indices of the reference (-1 without a result);
    `ReferenceSurface.body_face` turns them into (body id, face index).
    """

    distances: npt.NDArray[np.float32]
    face_ids: npt.NDArray[np.int32]


def signed_distances(
    points: FloatArray, bodies: list[Body], max_distance: float, tolerance: float, job: JobContext
) -> SignedDistances:
    """Signed distances from scan points to the nearest body surface."""
    job.progress(None, ProgressStage.PREPARING)
    with job.native(ProgressStage.PREPARING):
        reference = build_reference(
            [(str(index), body) for index, body in enumerate(bodies)],
            reference_deflection(tolerance),
        )
    return distances_to_reference(points, reference, max_distance, job)


def distances_to_reference(
    points: FloatArray, reference: ReferenceSurface, max_distance: float, job: JobContext | None
) -> SignedDistances:
    """Signed distances to a prepared reference; points farther than `max_distance` get NaN."""
    points = np.asarray(points, dtype=np.float64)
    distances = np.full(len(points), np.nan, dtype=np.float32)
    face_ids = np.full(len(points), -1, dtype=np.int32)
    if len(points) == 0:
        return SignedDistances(distances, face_ids)
    # The surface lies within one edge length of its nearest vertex, so points whose nearest
    # vertex is farther than max_distance + that length can have no result.
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
