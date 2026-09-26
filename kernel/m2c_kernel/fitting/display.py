"""Display geometry of construction primitives: a bounded surface patch and its outline.

A primitive is infinite (plane, cylinder, cone) or closed (sphere, torus); the
viewport shows the part of it that the fitted points cover, extended by 5 % on
each side (10 % in total), so the user sees where the construction lies
relative to the scan. Positions are in part coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit

MARGIN = 0.05
"""Margin on each side, relative to the covered extent."""

AROUND = 64
"""Segments around an axis."""

ALONG = 8
"""Segments along a cone or a meridian."""

type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class PatchGeometry:
    """Triangles of a surface patch and the segments (s, 2, 3) of its border."""

    positions: FloatArray
    faces: IntArray
    outline: FloatArray


def primitive_patch(primitive: Primitive, points: FloatArray) -> PatchGeometry:
    """Patch of `primitive` over the extent of `points`."""
    match primitive:
        case Plane():
            grid = _plane_grid(primitive, points)
        case Cylinder():
            grid = _cylinder_grid(primitive, points)
        case Cone():
            grid = _cone_grid(primitive, points)
        case Sphere():
            grid = _sphere_grid(primitive)
        case Torus():
            grid = _torus_grid(primitive)
    return PatchGeometry(grid.reshape(-1, 3), _grid_faces(grid), _outline(grid))


def plane_patch(
    origin: npt.ArrayLike, normal: npt.ArrayLike, x_dir: npt.ArrayLike, half_size: float
) -> PatchGeometry:
    """A square of `2 * half_size` centred on `origin`, one edge along `x_dir`."""
    o = np.asarray(origin, dtype=np.float64)
    e1 = unit(x_dir)
    e2 = np.cross(unit(normal), e1)
    corners = np.linspace(-half_size, half_size, 2)
    grid: FloatArray = o + corners[:, None, None] * e1 + corners[None, :, None] * e2
    return PatchGeometry(grid.reshape(-1, 3), _grid_faces(grid), _outline(grid))


def axis_segment(point: npt.ArrayLike, direction: npt.ArrayLike, half_length: float) -> FloatArray:
    """One segment (1, 2, 3) of an axis line, centred on `point`."""
    p = np.asarray(point, dtype=np.float64)
    d = unit(direction) * half_length
    segment: FloatArray = np.stack([p - d, p + d])[None, :, :]
    return segment


def _extent(values: FloatArray) -> tuple[float, float]:
    low, high = float(values.min()), float(values.max())
    margin = max(high - low, 1e-6) * MARGIN
    return low - margin, high + margin


def _plane_grid(plane: Plane, points: FloatArray) -> FloatArray:
    e1, e2 = frame_from_axis(plane.normal)
    origin = np.asarray(plane.origin, dtype=np.float64)
    relative = points - origin
    us = np.array(_extent(relative @ e1))
    vs = np.array(_extent(relative @ e2))
    grid: FloatArray = origin + us[:, None, None] * e1 + vs[None, :, None] * e2
    return grid


def _revolved_grid(
    origin: FloatArray, axis: FloatArray, heights: FloatArray, radii: FloatArray
) -> FloatArray:
    """Grid (len(heights), AROUND + 1, 3) of circles of `radii` at `heights` along `axis`."""
    e1, e2 = frame_from_axis(axis)
    angles = np.linspace(0.0, 2.0 * np.pi, AROUND + 1)
    ring = np.cos(angles)[:, None] * e1 + np.sin(angles)[:, None] * e2
    grid: FloatArray = (
        origin + heights[:, None, None] * axis + radii[:, None, None] * ring[None, :, :]
    )
    return grid


def _cylinder_grid(cylinder: Cylinder, points: FloatArray) -> FloatArray:
    axis = unit(cylinder.axis)
    origin = np.asarray(cylinder.origin, dtype=np.float64)
    heights = np.array(_extent((points - origin) @ axis))
    return _revolved_grid(origin, axis, heights, np.full(2, cylinder.radius))


def _cone_grid(cone: Cone, points: FloatArray) -> FloatArray:
    axis = unit(cone.axis)
    apex = np.asarray(cone.apex, dtype=np.float64)
    h0, h1 = _extent((points - apex) @ axis)
    heights = np.linspace(max(h0, 0.0), max(h1, 1e-6), ALONG + 1)
    return _revolved_grid(apex, axis, heights, heights * np.tan(cone.half_angle))


def _sphere_grid(sphere: Sphere) -> FloatArray:
    polar = np.linspace(0.0, np.pi, 2 * ALONG + 1)
    return _revolved_grid(
        np.asarray(sphere.center, dtype=np.float64),
        np.array([0.0, 0.0, 1.0]),
        -sphere.radius * np.cos(polar),
        sphere.radius * np.sin(polar),
    )


def _torus_grid(torus: Torus) -> FloatArray:
    tube = np.linspace(0.0, 2.0 * np.pi, 2 * ALONG + 1)
    return _revolved_grid(
        np.asarray(torus.center, dtype=np.float64),
        unit(torus.axis),
        torus.minor_radius * np.sin(tube),
        torus.major_radius + torus.minor_radius * np.cos(tube),
    )


def _grid_faces(grid: FloatArray) -> IntArray:
    rows, columns = grid.shape[:2]
    index = np.arange(rows * columns).reshape(rows, columns)
    a = index[:-1, :-1].ravel()
    b = index[1:, :-1].ravel()
    c = index[1:, 1:].ravel()
    d = index[:-1, 1:].ravel()
    faces: IntArray = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    return faces.astype(np.int64)


def _outline(grid: FloatArray) -> FloatArray:
    """Segments (s, 2, 3) along the four borders of the grid."""
    borders = (grid[0], grid[-1], grid[:, 0], grid[:, -1])
    segments = [np.stack([line[:-1], line[1:]], axis=1) for line in borders]
    outline: FloatArray = np.concatenate(segments)
    return outline
