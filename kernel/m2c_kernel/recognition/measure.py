"""Measurements of one relief on its plane: its contour, its top and its walls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.contours import (
    boundary_loops,
    inside_contour,
    section_loops,
    signed_area,
)
from m2c_kernel.recognition.planes import BasePlane

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]

UP_FACING = 0.9
INCLINED_SHARE = 0.6
"""The top's triangles rise above this share of the height (an inclined top's low end
lies well below its high end)."""
MIN_TILT_DEG = 2.0
TOP_SHARE = 0.1
"""Less upward area near the top than this share of the outline: no top face (a dome,
or a pocket without a floor: a through hole)."""
FLAT_TOP_FACTOR = 4.0
"""A top is flat when its points lie within this x the noise of a parallel plane."""
WALL_FACING = 0.5
WALL_STEP_MM = 0.5
MIN_WALL_SHARE = 0.3
"""A designed feature has steep walls: at least this share of perimeter x height.
Gentle bulges of a curved or tilted surface have next to none (measured: buttons with
rounded edges 0.4 and more, holes about 1.1, bulges 0 to 0.22)."""


@dataclass(frozen=True)
class PlaneContext:
    plane: BasePlane
    uvh: FloatArray
    faces: IntArray
    graph: sp.csr_matrix
    noise: float
    threshold: float
    footprint: FloatArray
    """(k, 3) edge equations of the plane's footprint (convex hull): n . p + d > 0 outside."""
    extent_area: float
    on_plane: BoolArray
    """Vertices of the base plane's own triangles."""
    facing: FloatArray
    """Cosine between each vertex normal and the plane normal."""
    normals: FloatArray


type TopKind = Literal["flat", "inclined", "domed", "through"]


@dataclass(frozen=True)
class Top:
    """The top of a boss or the floor of a pocket.

    `plane` is (a, b, c) of the plane h = a u + b v + c the top lies on (flat: a = b =
    0); None for a domed top and a through hole.
    """

    kind: TopKind
    plane: tuple[float, float, float] | None = None


def top_of(
    context: PlaneContext, part: IntArray, sign: float, level: float, height: float, area: float
) -> Top:
    """The top of a boss or the floor of a pocket, and the plane of a flat or inclined one.

    The top is made of the triangles near it that face up (out of the material,
    along the plane normal, for both). It is flat when their corners lie on a plane
    parallel to the base, inclined when they lie on a plane tilted by more than
    `MIN_TILT_DEG` that rises across the top by more than the flatness tolerance (the
    arms of a direction pad slope down towards its centre), domed otherwise.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    faces = context.faces[member[context.faces].any(axis=1)]
    corners = context.uvh[faces]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(normal, axis=1)
    facing = normal[:, 2] / np.maximum(double_area, 1e-300)
    rise = sign * (corners[:, :, 2].mean(axis=1) - level)
    up = (facing > UP_FACING) & (rise > INCLINED_SHARE * height)
    if 0.5 * float(double_area[up].sum()) < TOP_SHARE * area:
        return Top("through" if sign < 0 else "domed")
    points = context.uvh[np.unique(faces[up])]
    tolerance = max(FLAT_TOP_FACTOR * context.noise, 0.05)
    design = np.column_stack([points[:, :2], np.ones(len(points))])
    (a, b, c), *_ = np.linalg.lstsq(design, points[:, 2], rcond=None)
    if float(np.std(points[:, 2] - design @ (a, b, c))) >= tolerance:
        return Top("domed")
    tilted = np.degrees(np.arctan(np.hypot(a, b))) > MIN_TILT_DEG
    if tilted and float(np.ptp(design @ (a, b, c))) >= tolerance:
        return Top("inclined", (float(a), float(b), float(c)))
    if float(np.std(points[:, 2])) >= tolerance:
        return Top("domed")
    return Top("flat", (0.0, 0.0, float(np.mean(points[:, 2]))))


def section_contour(context: PlaneContext, part: IntArray, at: float) -> FloatArray | None:
    """The outer closed loop where the plane h = `at` cuts the triangles at the part.

    All triangles touching the part are cut, also those its search left out (a thin
    triangle whose own normal follows the noise), so the loop closes.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    loops = section_loops(context.uvh, context.faces[member[context.faces].any(axis=1)], at)
    if not loops:
        return None
    return max(loops, key=lambda loop: abs(signed_area(loop)))


def boundary_contour(context: PlaneContext, members: IntArray) -> FloatArray | None:
    """The outer boundary loop of the faces whose corners are all members (plane frame)."""
    if len(members) < 3:
        return None
    inside = np.zeros(len(context.uvh), dtype=bool)
    inside[members] = True
    faces = context.faces[inside[context.faces].all(axis=1)]
    if len(faces) == 0:
        return None
    loops = boundary_loops(faces)
    if not loops:
        return None
    uv = context.uvh[:, :2]
    outer = max(loops, key=lambda loop: abs(signed_area(uv[loop])))
    result: FloatArray = uv[outer]
    return result


def touches_level(context: PlaneContext, part: IntArray, level: float) -> bool:
    """Whether the part borders on scan points at its level (its rim reaches it).

    Coarse meshes have wall triangles that run from rim to rim, so the part itself
    may hold only its far rim; its neighbours then lie on the level.
    """
    neighbours = np.unique(context.graph[part].indices)
    near = np.abs(context.uvh[neighbours, 2] - level) < 2.0 * context.threshold
    own = np.abs(context.uvh[part, 2] - level) < 2.0 * context.threshold
    return bool(np.any(near) or np.any(own))


def walls_face(
    context: PlaneContext, part: IntArray, contour: FloatArray, height: float, *, outward: bool
) -> bool:
    """Whether the part has steep walls facing out of (boss) or into (pocket) the contour.

    The steep wall area must reach `MIN_WALL_SHARE` of perimeter x height. Each wall
    triangle at the part steps a little along its normal from its centre; for a boss
    the step leaves the outline, for a pocket it moves into the opening. Area weights
    keep a bore in a boss from outvoting the larger outer wall on meshes with as many
    points on both.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    touching = context.faces[member[context.faces].any(axis=1)]
    corners = context.uvh[touching]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(normal, axis=1)
    normal /= np.maximum(double_area, 1e-300)[:, None]
    wall = np.abs(normal[:, 2]) < WALL_FACING
    perimeter = float(np.linalg.norm(contour - np.roll(contour, -1, axis=0), axis=1).sum())
    if 0.5 * float(double_area[wall].sum()) < MIN_WALL_SHARE * perimeter * height:
        return False
    sideways = normal[wall, :2]
    sideways /= np.maximum(np.linalg.norm(sideways, axis=1, keepdims=True), 1e-9)
    stepped = corners[wall, :, :2].mean(axis=1) + WALL_STEP_MM * sideways
    weights = double_area[wall]
    inside = float(weights @ inside_contour(stepped, contour) / max(weights.sum(), 1e-300))
    return inside < 0.5 if outward else inside > 0.5
