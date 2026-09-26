"""Measurements between fitted shapes, reference geometry, origin items and body faces.

Every input is reduced to a plane (point, normal), an axis (point, direction), a point,
or, for faces without an analytic surface, the face itself:

| Pair                  | Distance                                   | Angle             |
|-----------------------|--------------------------------------------|-------------------|
| plane - plane         | only when parallel                         | between normals   |
| axis - axis           | parallel: between the lines; else shortest | between axes      |
| plane - axis          | only when parallel                         | axis to the plane |
| point - anything      | perpendicular / point to point             | -                 |
| face without analytic | minimum between the exact faces            | -                 |
| surface - face        |                                            |                   |

Cylinders and spheres also give a diameter. Values of fitted shapes carry a measured
uncertainty: the parameter covariance of the fit, `sigma^2 (J^T J)^-1` with the robust
sigma of the residuals (as in `fitting/constrained.py`), propagated by Monte Carlo
sampling, which also covers the kink of angles and distances at zero.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np

# OCP names missing from cad/occ_compat.py; see .work/interface-requests/T7.md.
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus

from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepExtrema_DistShapeShape,
    GeomAbs_Plane,
)
from m2c_kernel.document.results import Construction
from m2c_kernel.fitting.api import (
    Cone,
    Cylinder,
    Plane,
    Primitive,
    Sphere,
    Torus,
    robust_sigma,
    signed_distance,
)
from m2c_kernel.geometry import FloatArray, unit, vec3

type GeometryKind = Literal["plane", "axis", "point", "surface"]
type DistanceKind = Literal["parallel", "shortest", "point", "minimum"]
type OriginItem = Literal["XY", "YZ", "XZ", "X", "Y", "Z"]

PARALLEL_DEG = 0.5
"""Planes and axes closer to parallel than this count as parallel (distance defined)."""
UNCERTAINTY_POINTS = 5_000
UNCERTAINTY_SAMPLES = 400
_STEP = 1e-6


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
class FitCovariance:
    """Parameter covariance of a fitted primitive in a local parameterisation.

    `perturb(delta)` returns the primitive with the local parameters moved by `delta`.
    """

    covariance: FloatArray
    perturb: Callable[[FloatArray], Primitive]


@dataclass(frozen=True)
class Item:
    geometry: Geometry
    fit: FitCovariance | None = None


@dataclass(frozen=True)
class Measurement:
    """Distance in mm, angle in degrees (0-90), diameters in mm; sigmas are 1-sigma values."""

    distance: float | None
    distance_kind: DistanceKind | None
    angle: float | None
    parallel: bool
    diameter_a: float | None
    diameter_b: float | None
    distance_sigma: float | None = None
    angle_sigma: float | None = None
    diameter_a_sigma: float | None = None
    diameter_b_sigma: float | None = None


# --------------------------------------------------------------------------- geometry


def geometry_of_primitive(primitive: Primitive) -> Geometry:
    match primitive:
        case Plane(origin=origin, normal=normal):
            return Geometry("plane", np.asarray(origin, float), unit(np.asarray(normal)))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            return Geometry("axis", np.asarray(origin, float), unit(np.asarray(axis)), 2 * radius)
        case Cone(apex=apex, axis=axis):
            return Geometry("axis", np.asarray(apex, float), unit(np.asarray(axis)))
        case Sphere(center=center, radius=radius):
            return Geometry("point", np.asarray(center, float), None, 2.0 * radius)
        case Torus(center=center, axis=axis):
            return Geometry("axis", np.asarray(center, float), unit(np.asarray(axis)))


def geometry_of_construction(construction: Construction) -> Geometry | None:
    if construction.primitive is not None:
        return geometry_of_primitive(construction.primitive)
    if construction.axis is not None:
        axis = construction.axis
        return Geometry("axis", np.asarray(axis.point, float), unit(np.asarray(axis.direction)))
    if construction.point is not None:
        return Geometry("point", np.asarray(construction.point, float))
    return None


_ORIGIN: dict[OriginItem, tuple[GeometryKind, tuple[float, float, float]]] = {
    "XY": ("plane", (0.0, 0.0, 1.0)),
    "YZ": ("plane", (1.0, 0.0, 0.0)),
    "XZ": ("plane", (0.0, 1.0, 0.0)),
    "X": ("axis", (1.0, 0.0, 0.0)),
    "Y": ("axis", (0.0, 1.0, 0.0)),
    "Z": ("axis", (0.0, 0.0, 1.0)),
}


def geometry_of_origin(item: OriginItem) -> Geometry:
    kind, direction = _ORIGIN[item]
    return Geometry(kind, np.zeros(3), np.asarray(direction))


def _xyz(item: Any) -> FloatArray:
    return np.array([item.X(), item.Y(), item.Z()], dtype=np.float64)


def geometry_of_face(face: Any) -> Geometry:
    """The analytic surface of a B-Rep face, or the face itself for other surface types."""
    surface = BRepAdaptor_Surface(face, True)
    kind = surface.GetType()
    if kind == GeomAbs_Plane:
        plane = surface.Plane()
        return Geometry("plane", _xyz(plane.Location()), _xyz(plane.Axis().Direction()), None, face)
    if kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        axis = cylinder.Axis()
        diameter = 2.0 * cylinder.Radius()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), diameter, face)
    if kind == GeomAbs_Cone:
        axis = surface.Cone().Axis()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), None, face)
    if kind == GeomAbs_Sphere:
        sphere = surface.Sphere()
        return Geometry("point", _xyz(sphere.Location()), None, 2.0 * sphere.Radius(), face)
    if kind == GeomAbs_Torus:
        axis = surface.Torus().Axis()
        return Geometry("axis", _xyz(axis.Location()), _xyz(axis.Direction()), None, face)
    return Geometry("surface", np.zeros(3), shape=face)


# --------------------------------------------------------------------------- measuring


def measure(a: Geometry, b: Geometry | None) -> Measurement:
    """Closed-form measurement between two items (or the diameter of one)."""
    if b is None:
        return Measurement(None, None, None, False, a.diameter, None)
    distance, kind, angle, parallel = _relation(a, b)
    return Measurement(distance, kind, angle, parallel, a.diameter, b.diameter)


def _relation(
    a: Geometry, b: Geometry
) -> tuple[float | None, DistanceKind | None, float | None, bool]:
    if a.kind == "surface" or b.kind == "surface":
        distance = _face_distance(a, b)
        return distance, "minimum" if distance is not None else None, None, False
    if a.kind == "point" or b.kind == "point":
        point, other = (a, b) if a.kind == "point" else (b, a)
        return _point_distance(point.point, other), "point", None, False
    assert a.direction is not None and b.direction is not None
    cosine = abs(float(np.dot(a.direction, b.direction)))
    offset = b.point - a.point
    if a.kind == b.kind:
        angle = _degrees_from_cos(cosine)
        parallel = angle < PARALLEL_DEG
        if a.kind == "plane":
            if not parallel:
                return None, None, angle, False
            normal = unit(a.direction + np.sign(np.dot(a.direction, b.direction)) * b.direction)
            return abs(float(np.dot(offset, normal))), "parallel", angle, True
        if parallel:
            return float(np.linalg.norm(np.cross(offset, a.direction))), "parallel", angle, True
        normal = np.cross(a.direction, b.direction)
        distance = abs(float(np.dot(offset, normal))) / float(np.linalg.norm(normal))
        return distance, "shortest", angle, False
    plane, axis = (a, b) if a.kind == "plane" else (b, a)
    assert plane.direction is not None
    angle = 90.0 - _degrees_from_cos(cosine)
    if angle >= PARALLEL_DEG:
        return None, None, angle, False
    distance = abs(float(np.dot(axis.point - plane.point, plane.direction)))
    return distance, "parallel", angle, True


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


# --------------------------------------------------------------------------- uncertainty


def measure_items(a: Item, b: Item | None, rng: np.random.Generator) -> Measurement:
    """`measure` plus the 1-sigma uncertainty of every value that depends on a fit."""
    result = measure(a.geometry, None if b is None else b.geometry)
    a_fitted = a.fit is not None
    b_fitted = b is not None and b.fit is not None
    if not (a_fitted or b_fitted):
        return result
    first = _sample_geometries(a, rng)
    second = _sample_geometries(b, rng) if b is not None else [None] * UNCERTAINTY_SAMPLES
    values = [measure(x, y) for x, y in zip(first, second, strict=True)]

    def spread(pick: Callable[[Measurement], float | None], nominal: float | None) -> float | None:
        if nominal is None:
            return None
        drawn = np.array([pick(value) for value in values if pick(value) is not None], float)
        if len(drawn) < UNCERTAINTY_SAMPLES // 2:
            return None
        return float(np.sqrt(np.mean((drawn - nominal) ** 2)))

    return replace(
        result,
        distance_sigma=spread(lambda m: m.distance, result.distance),
        angle_sigma=spread(lambda m: m.angle, result.angle),
        diameter_a_sigma=spread(lambda m: m.diameter_a, result.diameter_a) if a_fitted else None,
        diameter_b_sigma=spread(lambda m: m.diameter_b, result.diameter_b) if b_fitted else None,
    )


def _sample_geometries(item: Item, rng: np.random.Generator) -> list[Geometry]:
    """The item's geometry drawn from its fit covariance (always the same without a fit)."""
    if item.fit is None:
        return [item.geometry] * UNCERTAINTY_SAMPLES
    fit = item.fit
    deltas = rng.multivariate_normal(
        np.zeros(len(fit.covariance)), fit.covariance, UNCERTAINTY_SAMPLES, method="eigh"
    )
    return [geometry_of_primitive(fit.perturb(delta)) for delta in deltas]


def fit_covariance(
    primitive: Primitive, points: FloatArray, rng: np.random.Generator
) -> FitCovariance | None:
    """Covariance of the primitive's parameters, estimated from the points it was fitted to."""
    if len(points) > UNCERTAINTY_POINTS:
        sample = points[rng.choice(len(points), UNCERTAINTY_POINTS, replace=False)]
    else:
        sample = points
    perturb = _parameterisation(primitive, sample)
    count = _parameter_count(primitive)
    if len(sample) <= count:
        return None
    residuals = signed_distance(primitive, sample)
    sigma = robust_sigma(residuals)
    jacobian = np.empty((len(sample), count))
    for k in range(count):
        step = np.zeros(count)
        step[k] = _STEP
        jacobian[:, k] = (
            signed_distance(perturb(step), sample) - signed_distance(perturb(-step), sample)
        ) / (2 * _STEP)
    information = jacobian.T @ jacobian
    if np.linalg.cond(information) > 1e12:
        return None
    # The subsample stands for all points: the information grows with the point count.
    covariance = sigma**2 * np.linalg.inv(information) * (len(sample) / len(points))
    return FitCovariance(covariance=covariance, perturb=perturb)


def _parameter_count(primitive: Primitive) -> int:
    return {"plane": 3, "cylinder": 5, "cone": 6, "sphere": 4, "torus": 7}[primitive.type]


def _tangents(direction: FloatArray) -> tuple[FloatArray, FloatArray]:
    helper = np.eye(3)[int(np.argmin(np.abs(direction)))]
    u = unit(np.cross(direction, helper))
    return u, np.cross(direction, u)


def _tilted(direction: FloatArray, u: FloatArray, v: FloatArray, delta: FloatArray) -> FloatArray:
    return unit(direction + delta[0] * u + delta[1] * v)


def _parameterisation(
    primitive: Primitive, points: FloatArray
) -> Callable[[FloatArray], Primitive]:
    """Local parameters around the fitted primitive.

    Directions tilt around the centroid of the points (plane) or around the axis point
    nearest to it (cylinder), which keeps offsets and tilts nearly uncorrelated.
    """
    centroid = points.mean(axis=0)
    match primitive:
        case Plane(origin=origin, normal=normal):
            n = unit(np.asarray(normal))
            u, v = _tangents(n)
            anchor = centroid - np.dot(centroid - np.asarray(origin), n) * n

            def plane(delta: FloatArray) -> Primitive:
                tilted = _tilted(n, u, v, delta)
                return Plane(origin=vec3(anchor + delta[2] * n), normal=vec3(tilted))

            return plane
        case Cylinder(origin=origin, axis=axis, radius=radius):
            a = unit(np.asarray(axis))
            u, v = _tangents(a)
            anchor = np.asarray(origin) + np.dot(centroid - np.asarray(origin), a) * a

            def cylinder(delta: FloatArray) -> Primitive:
                return Cylinder(
                    origin=vec3(anchor + delta[2] * u + delta[3] * v),
                    axis=vec3(_tilted(a, u, v, delta)),
                    radius=radius + delta[4],
                )

            return cylinder
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            a = unit(np.asarray(axis))
            u, v = _tangents(a)

            def cone(delta: FloatArray) -> Primitive:
                shift = delta[2] * u + delta[3] * v + delta[4] * a
                return Cone(
                    apex=vec3(np.asarray(apex) + shift),
                    axis=vec3(_tilted(a, u, v, delta)),
                    half_angle=half_angle + delta[5],
                )

            return cone
        case Sphere(center=center, radius=radius):

            def sphere(delta: FloatArray) -> Primitive:
                return Sphere(center=vec3(np.asarray(center) + delta[:3]), radius=radius + delta[3])

            return sphere
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            a = unit(np.asarray(axis))
            u, v = _tangents(a)

            def torus(delta: FloatArray) -> Primitive:
                return Torus(
                    center=vec3(np.asarray(center) + delta[2:5]),
                    axis=vec3(_tilted(a, u, v, delta)),
                    major_radius=major + delta[5],
                    minor_radius=minor + delta[6],
                )

            return torus
