"""Primitive parameterisation and signed distances, shared by every module.

| Kind     | Parameters                                   | Signed distance          |
|----------|----------------------------------------------|--------------------------|
| plane    | origin o, normal n                           | (p - o) . n              |
| sphere   | centre c, radius r                           | |p - c| - r              |
| cylinder | axis point o, axis a, radius r               | rho - r                  |
| cone     | apex v, axis a (apex to opening), half angle | rho cos(al) - h sin(al)  |
| torus    | centre c, axis a, major R, minor r           | sqrt((rho-R)^2+h^2) - r  |

`h` is the coordinate along the axis and `rho` the distance from it. Positive
distances lie on the side the outward normal of the convex primitive points to.
Angles are radians. All positions are in millimetres, part coordinates unless a
caller says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray, Vec3, unit

type PrimitiveKind = Literal["plane", "cylinder", "cone", "sphere", "torus"]

PRIMITIVE_KINDS: tuple[PrimitiveKind, ...] = ("plane", "sphere", "cylinder", "cone", "torus")
"""All kinds, ordered from the fewest to the most parameters."""


@dataclass(frozen=True, kw_only=True)
class Plane:
    type: Literal["plane"] = "plane"
    origin: Vec3
    normal: Vec3


@dataclass(frozen=True, kw_only=True)
class Cylinder:
    type: Literal["cylinder"] = "cylinder"
    origin: Vec3
    axis: Vec3
    radius: float


@dataclass(frozen=True, kw_only=True)
class Cone:
    type: Literal["cone"] = "cone"
    apex: Vec3
    axis: Vec3
    half_angle: float


@dataclass(frozen=True, kw_only=True)
class Sphere:
    type: Literal["sphere"] = "sphere"
    center: Vec3
    radius: float


@dataclass(frozen=True, kw_only=True)
class Torus:
    type: Literal["torus"] = "torus"
    center: Vec3
    axis: Vec3
    major_radius: float
    minor_radius: float


type Primitive = Plane | Cylinder | Cone | Sphere | Torus


@dataclass(frozen=True, kw_only=True)
class Axis:
    """An infinite line: a point on it and a unit direction."""

    point: Vec3
    direction: Vec3


def _axial(points: FloatArray, origin: Vec3, axis: Vec3) -> tuple[FloatArray, FloatArray]:
    """Coordinate along the axis (h) and distance from the axis (rho)."""
    relative = points - np.asarray(origin)
    h = relative @ np.asarray(axis)
    rho = np.sqrt(np.maximum(np.einsum("ij,ij->i", relative, relative) - h * h, 0.0))
    return h, rho


def signed_distance(primitive: Primitive, points: npt.ArrayLike) -> FloatArray:
    """Signed distance of (n, 3) points to the primitive surface."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    match primitive:
        case Plane(origin=origin, normal=normal):
            result: FloatArray = (p - np.asarray(origin)) @ np.asarray(normal)
            return result
        case Sphere(center=center, radius=radius):
            distance: FloatArray = np.linalg.norm(p - np.asarray(center), axis=1) - radius
            return distance
        case Cylinder(origin=origin, axis=axis, radius=radius):
            _, rho = _axial(p, origin, axis)
            return rho - radius
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            h, rho = _axial(p, apex, axis)
            slanted: FloatArray = rho * np.cos(half_angle) - h * np.sin(half_angle)
            return slanted
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            h, rho = _axial(p, center, axis)
            return np.hypot(rho - major, h) - minor


def surface_normals(primitive: Primitive, points: npt.ArrayLike, step: float = 1e-4) -> FloatArray:
    """Unit gradient of the signed distance: the outward surface normal near each point."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    gradient = np.stack(
        [
            signed_distance(primitive, p + offset) - signed_distance(primitive, p - offset)
            for offset in np.eye(3) * step
        ],
        axis=1,
    )
    return unit(gradient)
