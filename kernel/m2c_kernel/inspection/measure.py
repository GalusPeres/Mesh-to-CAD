"""Measurements between fitted shapes, reference geometry and body faces, in closed form.

Every input is reduced to a plane, an axis (with a diameter for cylinders, spheres
and tori) or a point. Distances are defined for parallel planes and axes and for
anything involving a point; angles for planes and axes. Two body faces without an
analytic surface fall back to the minimum distance between the exact faces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

# Not (yet) re-exported by cad/occ_compat.py; see .work/interface-requests/T7.md.
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.GeomAbs import (
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)

from m2c_kernel.document.results import Construction
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Sphere, Torus
from m2c_kernel.geometry import FloatArray, unit

type GeometryKind = Literal["plane", "axis", "point", "surface"]

PARALLEL_DEG = 0.5
"""Planes and axes closer to parallel than this count as parallel (distance defined)."""


@dataclass(frozen=True)
class Geometry:
    """A measurable item: a plane (point, normal), an axis (point, direction) or a point."""

    kind: GeometryKind
    point: FloatArray
    direction: FloatArray | None = None
    diameter: float | None = None
    shape: Any = None
    """The exact face, for the minimum-distance fallback."""


@dataclass(frozen=True)
class Measurement:
    distance: float | None
    angle: float | None
    """Degrees, 0 to 90."""
    parallel: bool


def from_construction(construction: Construction) -> Geometry | None:
    if construction.primitive is not None:
        return _from_primitive(construction.primitive)
    if construction.axis is not None:
        axis = construction.axis
        return Geometry("axis", np.asarray(axis.point, float), unit(axis.direction))
    if construction.point is not None:
        return Geometry("point", np.asarray(construction.point, float))
    return None


def _from_primitive(primitive: Plane | Cylinder | Cone | Sphere | Torus) -> Geometry:
    match primitive:
        case Plane(origin=origin, normal=normal):
            return Geometry("plane", np.asarray(origin, float), unit(normal))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            return Geometry("axis", np.asarray(origin, float), unit(axis), 2.0 * radius)
        case Cone(apex=apex, axis=axis):
            return Geometry("axis", np.asarray(apex, float), unit(axis))
        case Sphere(center=center, radius=radius):
            return Geometry("point", np.asarray(center, float), None, 2.0 * radius)
        case Torus(center=center, axis=axis, major_radius=major):
            return Geometry("axis", np.asarray(center, float), unit(axis), 2.0 * major)


def _xyz(item: Any) -> FloatArray:
    return np.array([item.X(), item.Y(), item.Z()], dtype=np.float64)


def from_face(face: Any) -> Geometry:
    """The analytic surface of a B-Rep face, or the face itself for other surface types."""
    surface = BRepAdaptor_Surface(face, True)
    kind = surface.GetType()
    if kind == GeomAbs_Plane:
        plane = surface.Plane()
        return Geometry("plane", _xyz(plane.Location()), _xyz(plane.Axis().Direction()), shape=face)
    if kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        axis = cylinder.Axis()
        diameter = 2.0 * cylinder.Radius()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), diameter, face)
    if kind == GeomAbs_Cone:
        axis = surface.Cone().Axis()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), shape=face)
    if kind == GeomAbs_Sphere:
        sphere = surface.Sphere()
        return Geometry("point", _xyz(sphere.Location()), None, 2.0 * sphere.Radius(), face)
    if kind == GeomAbs_Torus:
        torus = surface.Torus()
        axis = torus.Axis()
        diameter = 2.0 * torus.MajorRadius()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), diameter, face)
    return Geometry("surface", np.zeros(3), shape=face)


def measure(a: Geometry, b: Geometry) -> Measurement:
    if a.kind == "surface" or b.kind == "surface":
        return Measurement(_face_distance(a, b), None, False)
    if a.kind == "point" or b.kind == "point":
        point, other = (a, b) if a.kind == "point" else (b, a)
        return Measurement(_point_distance(point.point, other), None, False)
    assert a.direction is not None and b.direction is not None
    cosine = abs(float(np.dot(a.direction, b.direction)))
    offset = b.point - a.point
    if a.kind == "plane" and b.kind == "plane":
        angle = _degrees_from_cos(cosine)
        parallel = angle < PARALLEL_DEG
        normal = unit(a.direction + np.sign(np.dot(a.direction, b.direction)) * b.direction)
        distance = abs(float(np.dot(offset, normal))) if parallel else None
        return Measurement(distance, angle, parallel)
    if a.kind == "axis" and b.kind == "axis":
        angle = _degrees_from_cos(cosine)
        parallel = angle < PARALLEL_DEG
        if parallel:
            distance = float(np.linalg.norm(np.cross(offset, a.direction)))
        else:
            normal = np.cross(a.direction, b.direction)
            distance = abs(float(np.dot(offset, normal))) / float(np.linalg.norm(normal))
        return Measurement(distance, angle, parallel)
    plane, axis = (a, b) if a.kind == "plane" else (b, a)
    assert plane.direction is not None
    # Angle between an axis and a plane: 90 degrees minus the angle to the plane normal.
    angle = 90.0 - _degrees_from_cos(cosine)
    parallel = angle < PARALLEL_DEG
    distance = abs(float(np.dot(axis.point - plane.point, plane.direction))) if parallel else None
    return Measurement(distance, angle, parallel)


def _degrees_from_cos(cosine: float) -> float:
    return float(np.degrees(np.arccos(np.clip(cosine, 0.0, 1.0))))


def _point_distance(point: FloatArray, other: Geometry) -> float:
    offset = point - other.point
    if other.kind == "plane":
        assert other.direction is not None
        return abs(float(np.dot(offset, other.direction)))
    if other.kind == "axis":
        assert other.direction is not None
        return float(np.linalg.norm(np.cross(offset, other.direction)))
    return float(np.linalg.norm(offset))


def _face_distance(a: Geometry, b: Geometry) -> float | None:
    if a.shape is None or b.shape is None:
        return None
    extrema = BRepExtrema_DistShapeShape(a.shape, b.shape)
    if not extrema.IsDone():
        return None
    return float(extrema.Value())
