"""Detection of the large planes of a scan, for the automatic alignment.

Deterministic and vectorised: the dominant face-normal direction is found by scoring
candidate normals (drawn with a seeded generator) on an area-weighted subsample; the
faces in that direction are split by their offset along it, the most populated offset
band is fitted with `fitting.api.fit_primitive` and its inliers are removed. Repeat
until the remaining planes are small.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from m2c_kernel.fitting.api import FitError, fit_primitive
from m2c_kernel.geometry import FloatArray, unit

_CONE_COS = float(np.cos(np.radians(15.0)))
_MEMBER_COS = float(np.cos(np.radians(25.0)))
_SCORE_SAMPLE = 40_000
_CANDIDATES = 200
_MAX_PLANES = 8
_MIN_AREA_RATIO = 0.02


@dataclass(frozen=True)
class PlaneCandidate:
    point: FloatArray
    normal: FloatArray
    """Outward normal (the side the face normals point to)."""
    area: float
    rms: float
    faces: np.ndarray


def face_geometry(
    vertices: FloatArray, faces: np.ndarray
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Unit face normals, face areas and face centroids."""
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    cross = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    return unit(cross), area, (a + b + c) / 3.0


def detect_planes(
    vertices: FloatArray,
    faces: np.ndarray,
    band: float,
    rng: np.random.Generator,
    usable: np.ndarray | None = None,
) -> list[PlaneCandidate]:
    """Large planes, largest area first. `band` is the inlier distance in mm."""
    normals, areas, centroids = face_geometry(vertices, faces)
    remaining = np.ones(len(faces), dtype=bool) if usable is None else usable.copy()
    total_area = float(areas[remaining].sum())
    planes: list[PlaneCandidate] = []
    while len(planes) < _MAX_PLANES and remaining.any():
        direction = _dominant_direction(normals, areas, remaining, rng)
        if direction is None:
            break
        plane = _plane_along(direction, normals, areas, centroids, remaining, band, rng)
        if plane is None:
            break
        remaining[plane.faces] = False
        if plane.area < _MIN_AREA_RATIO * total_area:
            # Removing its faces lets the search continue with other directions.
            continue
        planes.append(plane)
    planes.sort(key=lambda item: -item.area)
    return planes


def _dominant_direction(
    normals: FloatArray, areas: FloatArray, remaining: np.ndarray, rng: np.random.Generator
) -> FloatArray | None:
    index = np.nonzero(remaining)[0]
    weights = areas[index]
    total = float(weights.sum())
    if total <= 0.0:
        return None
    probability = weights / total
    sample = rng.choice(index, size=min(_SCORE_SAMPLE, len(index)), p=probability)
    candidates = normals[rng.choice(index, size=min(_CANDIDATES, len(index)), p=probability)]
    scores = ((normals[sample] @ candidates.T) > _CONE_COS).sum(axis=0)
    best = candidates[int(np.argmax(scores))]
    members = sample[(normals[sample] @ best) > _CONE_COS]
    return unit((areas[members, None] * normals[members]).sum(axis=0))


def _plane_along(
    direction: FloatArray,
    normals: FloatArray,
    areas: FloatArray,
    centroids: FloatArray,
    remaining: np.ndarray,
    band: float,
    rng: np.random.Generator,
) -> PlaneCandidate | None:
    cone = np.nonzero(remaining & ((normals @ direction) > _CONE_COS))[0]
    if len(cone) < 3:
        return None
    offsets = centroids[cone] @ direction
    low, high = float(offsets.min()), float(offsets.max())
    bins = max(1, int(np.ceil((high - low) / band)))
    histogram, edges = np.histogram(
        offsets, bins=bins, range=(low, low + bins * band), weights=areas[cone]
    )
    peak = int(np.argmax(histogram))
    centre = 0.5 * (edges[peak] + edges[peak + 1])
    seed = cone[np.abs(offsets - centre) <= band]
    if len(seed) < 3:
        return None
    point, normal = centroids[seed].mean(axis=0), direction
    members = seed
    for _ in range(2):
        try:
            fit = fit_primitive("plane", centroids[members], normals[members], rng)
        except FitError:
            return None
        point = np.asarray(fit.primitive.origin)  # type: ignore[union-attr]
        normal = unit(np.asarray(fit.primitive.normal))  # type: ignore[union-attr]
        distance = np.abs((centroids - point) @ normal)
        members = np.nonzero(remaining & (distance <= band) & ((normals @ normal) > _MEMBER_COS))[0]
        if len(members) < 3:
            return None
    distance = (centroids[members] - point) @ normal
    return PlaneCandidate(
        point=point,
        normal=normal,
        area=float(areas[members].sum()),
        rms=float(np.sqrt(np.mean(distance**2))),
        faces=members,
    )
