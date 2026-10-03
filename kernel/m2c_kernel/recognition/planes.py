"""Base planes: the large flat faces of a part, found robustly despite details on them.

Greedy, largest area first:

1. The dominant normal direction of the remaining triangles (area-weighted, summed
   over a 10 degree cone on a Fibonacci sphere of directions).
2. Along that direction, the most common offset of those triangles (area-weighted
   histogram): one flat level.
3. A robust plane fit (Tukey weights) through the triangles near that level; the
   inliers are the triangles within a few noise widths whose normals agree.
4. Accepted when the inliers cover enough of the part's area; the inliers are
   removed and the search repeats.

Buttons, bosses and pockets on a face barely move the fit, because their triangles
lie on other levels or face other ways.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]

DIRECTIONS = 2_000
CONE_DEG = 10.0
NORMAL_DEG = 15.0
LEVEL_BIN_MM = 0.05
MIN_SHARE = 0.03
"""A base plane covers at least this share of the part's area."""
MAX_PLANES = 16
MAX_TRIES = 40


@dataclass(frozen=True)
class BasePlane:
    """A flat face of the part.

    Attributes:
        origin: Centre of the inlier area, on the plane.
        normal: Unit normal, pointing out of the material.
        x_axis: In-plane unit axis along the face's longer extent.
        faces: Inlier triangles.
        area: Inlier area (mm^2).
        rms: RMS distance of the inlier vertices to the plane (mm).
    """

    origin: FloatArray
    normal: FloatArray
    x_axis: FloatArray
    faces: IntArray
    area: float
    rms: float

    @property
    def y_axis(self) -> FloatArray:
        result: FloatArray = np.cross(self.normal, self.x_axis)
        return result

    def to_plane(self, points: FloatArray) -> FloatArray:
        """(n, 3) points as (u, v, h): in-plane coordinates and height above the plane."""
        offset = points - self.origin
        result: FloatArray = np.column_stack(
            [offset @ self.x_axis, offset @ self.y_axis, offset @ self.normal]
        )
        return result

    def from_plane(self, uvh: FloatArray) -> FloatArray:
        result: FloatArray = (
            self.origin
            + uvh[:, :1] * self.x_axis
            + uvh[:, 1:2] * self.y_axis
            + uvh[:, 2:3] * self.normal
        )
        return result


def fibonacci_sphere(count: int) -> FloatArray:
    index = np.arange(count) + 0.5
    polar = np.arccos(1.0 - 2.0 * index / count)
    azimuth = np.pi * (1.0 + 5.0**0.5) * index
    result: FloatArray = np.column_stack(
        [np.cos(azimuth) * np.sin(polar), np.sin(azimuth) * np.sin(polar), np.cos(polar)]
    )
    return result


def base_planes(
    vertices: FloatArray, faces: IntArray, noise: float, *, min_share: float = MIN_SHARE
) -> list[BasePlane]:
    """The part's large flat faces, largest first."""
    corners = vertices[faces]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(cross, axis=1)
    areas = double_area / 2.0
    normals = cross / np.maximum(double_area, 1e-300)[:, None]
    centroids = corners.mean(axis=1)
    total = float(areas.sum())

    directions = fibonacci_sphere(DIRECTIONS)
    _, bins = cKDTree(directions).query(normals)
    cone = cKDTree(directions).query_ball_point(
        directions, 2.0 * np.sin(np.radians(CONE_DEG) / 2.0)
    )
    remaining = np.ones(len(faces), dtype=bool)
    tried = np.zeros(DIRECTIONS, dtype=bool)
    planes: list[BasePlane] = []
    for _ in range(MAX_TRIES):
        if len(planes) >= MAX_PLANES:
            break
        bin_area = np.bincount(bins[remaining], weights=areas[remaining], minlength=DIRECTIONS)
        cone_area = np.array([bin_area[members].sum() for members in cone])
        cone_area[tried] = 0.0
        best = int(np.argmax(cone_area))
        if cone_area[best] < min_share * total:
            break
        tried[cone[best]] = True
        plane = _plane_along(
            directions[best], vertices, faces, normals, areas, centroids, remaining, noise
        )
        if plane is None or plane.area < min_share * total:
            continue
        remaining[plane.faces] = False
        planes.append(plane)
    return planes


def _plane_along(
    direction: FloatArray,
    vertices: FloatArray,
    faces: IntArray,
    normals: FloatArray,
    areas: FloatArray,
    centroids: FloatArray,
    remaining: BoolArray,
    noise: float,
) -> BasePlane | None:
    facing = remaining & (normals @ direction > np.cos(np.radians(CONE_DEG)))
    if not np.any(facing):
        return None
    offsets = centroids[facing] @ direction
    low, high = offsets.min(), offsets.max()
    count = max(int((high - low) / LEVEL_BIN_MM) + 1, 1)
    histogram, edges = np.histogram(offsets, bins=count, weights=areas[facing])
    histogram = np.convolve(histogram, np.ones(3), mode="same")
    level = float((edges[np.argmax(histogram)] + edges[np.argmax(histogram) + 1]) / 2.0)
    band = max(0.5, 10.0 * noise)
    near = np.flatnonzero(facing)[np.abs(offsets - level) < band]
    points = vertices[np.unique(faces[near])]
    origin, normal, rms = robust_plane(points, direction)
    if normal @ direction < 0:
        normal = -normal
    tolerance = max(4.0 * noise, 0.05)
    distance = np.abs((centroids - origin) @ normal)
    agree = normals @ normal > np.cos(np.radians(NORMAL_DEG))
    inliers = np.flatnonzero(remaining & agree & (distance < tolerance))
    if len(inliers) < 3:
        return None
    inlier_points = vertices[np.unique(faces[inliers])]
    centre = inlier_points.mean(axis=0)
    centre = centre - ((centre - origin) @ normal) * normal
    flat = inlier_points - centre
    flat -= np.outer(flat @ normal, normal)
    _, _, axes = np.linalg.svd(flat, full_matrices=False)
    x_axis = axes[0] - (axes[0] @ normal) * normal
    x_axis /= np.linalg.norm(x_axis)
    return BasePlane(
        origin=centre,
        normal=normal,
        x_axis=x_axis,
        faces=inliers.astype(np.int64),
        area=float(areas[inliers].sum()),
        rms=rms,
    )


def robust_plane(
    points: FloatArray, guess: FloatArray, iterations: int = 8
) -> tuple[FloatArray, FloatArray, float]:
    """Plane through points by iteratively reweighted least squares (Tukey biweight)."""
    weights = np.ones(len(points))
    normal = guess / np.linalg.norm(guess)
    origin = points.mean(axis=0)
    residual = np.zeros(len(points))
    for _ in range(iterations):
        w = weights / max(weights.sum(), 1e-300)
        origin = (points * w[:, None]).sum(axis=0)
        centred = points - origin
        covariance = (centred * w[:, None]).T @ centred
        _, vectors = np.linalg.eigh(covariance)
        normal = vectors[:, 0]
        residual = centred @ normal
        scale = max(1.4826 * float(np.median(np.abs(residual))), 1e-4)
        u = residual / (4.685 * scale)
        weights = np.where(np.abs(u) < 1.0, (1.0 - u**2) ** 2, 0.0)
    inlier = weights > 0
    rms = float(np.sqrt(np.mean(residual[inlier] ** 2))) if np.any(inlier) else 0.0
    return origin, normal, rms
