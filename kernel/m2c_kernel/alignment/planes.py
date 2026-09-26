"""Detection of the large planes of a scan, for the automatic alignment.

Planes are searched on a fixed-size subsample of the faces: the dominant face-normal
direction is found by scoring candidate normals (drawn with a seeded generator) by the
area they cover within 15 degrees; the faces around that direction are split by their
offset along it and the most populated offset band is fitted with
`fitting.api.fit_primitive`. Its faces leave the search and the next direction is
scored. Each accepted plane is finally refitted on all faces within the inlier band,
so the subsample only decides where planes are, not how exactly they lie.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.api import FitError, fit_primitive, robust_sigma
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.mesh.normals import vertex_normals

_CONE_COS = float(np.cos(np.radians(15.0)))
_MEMBER_COS = float(np.cos(np.radians(10.0)))
_SEARCH_FACES = 120_000
_SCORE_FACES = 30_000
_CANDIDATES = 160
_MAX_PLANES = 8
_MAX_ROUNDS = 24
MIN_AREA_RATIO = 0.02
"""Planes smaller than this share of the scan area are ignored."""

type IntArray = npt.NDArray[np.int64]
type Mask = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class PlaneCandidate:
    point: FloatArray
    normal: FloatArray
    """Outward normal: the side the face normals point to."""
    area: float
    rms: float
    faces: IntArray


@dataclass(frozen=True)
class _FaceData:
    normals: FloatArray
    areas: FloatArray
    centroids: FloatArray


def face_data(vertices: FloatArray, faces: IntArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Smoothed unit face normals, face areas and face centroids.

    The normal of a face is the mean of its vertex normals, which averages over the
    two-ring. Raw face normals of a dense, noisy scan scatter by more than the cones
    used here (1 mm triangles with 0.05 mm noise: several degrees).
    """
    corners = vertices[faces]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    smoothed = vertex_normals(vertices, faces)[faces].sum(axis=1)
    return unit(smoothed), area, corners.mean(axis=1)


def detect_planes(
    vertices: FloatArray,
    faces: IntArray,
    band: float,
    rng: np.random.Generator,
    usable: Mask | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> list[PlaneCandidate]:
    """Large planes, largest area first. `band` is the inlier distance in mm."""
    normals, areas, centroids = face_data(vertices, faces)
    allowed = np.ones(len(faces), dtype=bool) if usable is None else usable.astype(bool)
    candidates = np.nonzero(allowed)[0]
    total_area = float(areas[candidates].sum())
    if len(candidates) < 3 or total_area <= 0.0:
        return []
    search = np.sort(rng.choice(candidates, min(_SEARCH_FACES, len(candidates)), replace=False))
    data = _FaceData(normals, areas, centroids)
    scale = len(candidates) / len(search)
    min_area = MIN_AREA_RATIO * total_area
    remaining = np.ones(len(search), dtype=bool)
    planes: list[PlaneCandidate] = []
    for _ in range(_MAX_ROUNDS):
        if len(planes) == _MAX_PLANES:
            break
        if check_cancelled is not None:
            check_cancelled()
        direction, support = _dominant_direction(data, search[remaining], rng)
        if direction is None or support * scale < min_area:
            break
        members = _plane_members(data, search, remaining, direction, band, rng)
        if members is None:
            break
        remaining[members] = False
        plane = _refit_all(data, allowed, search[members], band, rng)
        if plane is not None and plane.area >= min_area:
            planes.append(plane)
    planes.sort(key=lambda item: -item.area)
    return _distinct(planes, band)


def _dominant_direction(
    data: _FaceData, faces: IntArray, rng: np.random.Generator
) -> tuple[FloatArray | None, float]:
    """The face-normal direction that covers the most area within 15 degrees."""
    if len(faces) < 3:
        return None, 0.0
    weights = data.areas[faces]
    total = float(weights.sum())
    if total <= 0.0:
        return None, 0.0
    probability = weights / total
    score_faces = faces[rng.choice(len(faces), min(_SCORE_FACES, len(faces)), p=probability)]
    trial = data.normals[faces[rng.choice(len(faces), min(_CANDIDATES, len(faces)), p=probability)]]
    covered = (data.normals[score_faces] @ trial.T) > _CONE_COS
    best = int(np.argmax(covered.sum(axis=0)))
    in_cone = faces[(data.normals[faces] @ trial[best]) > _CONE_COS]
    direction = unit((data.areas[in_cone, None] * data.normals[in_cone]).sum(axis=0))
    return direction, float(data.areas[in_cone].sum())


def _plane_members(
    data: _FaceData,
    search: IntArray,
    remaining: Mask,
    direction: FloatArray,
    band: float,
    rng: np.random.Generator,
) -> IntArray | None:
    """Positions in `search` of the most populated offset band along `direction`.

    Returns None only when the direction has no faces left. A band that cannot be
    fitted still removes its faces, so the search moves on.
    """
    cone = np.nonzero(remaining & ((data.normals[search] @ direction) > _CONE_COS))[0]
    if len(cone) == 0:
        return None
    offsets = data.centroids[search[cone]] @ direction
    low = float(offsets.min())
    bins = max(1, int(np.ceil((float(offsets.max()) - low) / band)) + 1)
    histogram = np.bincount(
        ((offsets - low) / band).astype(np.int64), weights=data.areas[search[cone]], minlength=bins
    )
    peak = int(np.argmax(histogram))
    centre = low + (peak + 0.5) * band
    aligned = (data.normals[search[cone]] @ direction) > _MEMBER_COS
    seed = cone[(np.abs(offsets - centre) <= 1.5 * band) & aligned]
    if len(seed) < 3:
        return seed
    try:
        fit = fit_primitive("plane", data.centroids[search[seed]], data.normals[search[seed]], rng)
    except FitError:
        return seed
    point = np.asarray(fit.primitive.origin)  # type: ignore[union-attr]
    normal = unit(np.asarray(fit.primitive.normal))  # type: ignore[union-attr]
    distance = np.abs((data.centroids[search] - point) @ normal)
    near = remaining & (distance <= band) & (np.abs(data.normals[search] @ normal) > _MEMBER_COS)
    return np.nonzero(near)[0] if near.any() else seed


def _refit_all(
    data: _FaceData, allowed: Mask, seed: IntArray, band: float, rng: np.random.Generator
) -> PlaneCandidate | None:
    """Fit the plane to its search faces, then refine it on all faces near it.

    The first refinements use a wider band: a slightly tilted start plane would
    otherwise keep only one end of the face and stay tilted.
    """
    members = seed
    point = normal = np.zeros(3)
    for width in (3.0 * band, 2.0 * band, band, band):
        if len(members) < 3:
            return None
        try:
            fit = fit_primitive("plane", data.centroids[members], data.normals[members], rng)
        except FitError:
            return None
        point = np.asarray(fit.primitive.origin)  # type: ignore[union-attr]
        normal = unit(np.asarray(fit.primitive.normal))  # type: ignore[union-attr]
        if float(data.normals[members] @ normal @ data.areas[members]) < 0:
            normal = -normal
        distance = (data.centroids - point) @ normal
        members = np.nonzero(
            allowed & (np.abs(distance) <= width) & ((data.normals @ normal) > _MEMBER_COS)
        )[0]
    if len(members) < 3:
        return None
    residual = (data.centroids[members] - point) @ normal
    if robust_sigma(residual) > band / 3.0:
        # Residuals spread evenly over the band: a curved patch cut by it, not a plane.
        return None
    return PlaneCandidate(
        point=point,
        normal=normal,
        area=float(data.areas[members].sum()),
        rms=float(np.sqrt(np.mean(residual**2))),
        faces=members,
    )


def _distinct(planes: list[PlaneCandidate], band: float) -> list[PlaneCandidate]:
    """Drop planes that the refit turned into a copy of a larger one."""
    kept: list[PlaneCandidate] = []
    for plane in planes:
        duplicate = any(
            float(plane.normal @ other.normal) > _CONE_COS
            and abs(float((plane.point - other.point) @ other.normal)) <= band
            for other in kept
        )
        if not duplicate:
            kept.append(plane)
    return kept
