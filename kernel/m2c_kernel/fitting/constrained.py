"""Fits with fixed parameters and direction relations, plus parameter uncertainties.

A constrained fit starts from a free fit (or any start primitive) and refines
only the parameters the constraints leave free, with the same soft-L1 loss as
`fit.py`. Directions are either free (two local parameters around the start
direction), fixed, or perpendicular to a given vector (one angle). After the
solve, the standard uncertainty of every free parameter comes from the plain
least-squares Jacobian: `cov = sigma^2 (J^T J)^-1` with the robust sigma.
Uncertainties are reported in millimetres and degrees under the parameter names
used by the fit tool: `direction`, `offset`, `radius`, `halfAngle`,
`majorRadius`, `minorRadius`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.fitting.fit import (
    MAX_REFINE_POINTS,
    FitError,
    fit_primitive,
    robust_sigma,
)
from m2c_kernel.fitting.primitives import (
    Cone,
    Cylinder,
    Plane,
    Primitive,
    PrimitiveKind,
    Sphere,
    Torus,
    signed_distance,
)
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit, vec3


@dataclass(frozen=True, kw_only=True)
class Constraints:
    """Values the fit must keep. Directions are unit vectors in part coordinates.

    `direction` is the plane normal or the axis; `perpendicular_to` forces the
    direction perpendicular to a vector. `point` lies on the plane, on the axis
    (cylinder), is the apex (cone) or the centre (sphere, torus). `offset` is the
    signed distance of a plane from the part origin along its normal.
    """

    direction: FloatArray | None = None
    perpendicular_to: FloatArray | None = None
    point: FloatArray | None = None
    radius: float | None = None
    half_angle: float | None = None
    major_radius: float | None = None
    minor_radius: float | None = None
    offset: float | None = None


@dataclass(frozen=True)
class ConstrainedFit:
    primitive: Primitive
    rms: float
    uncertainty: dict[str, float]


class _Vector:
    """Free parameters of a model, collected while the model is built."""

    def __init__(self) -> None:
        self.start: list[float] = []
        self.names: list[str] = []

    def add(self, name: str, value: float) -> int:
        self.start.append(float(value))
        self.names.append(name)
        return len(self.start) - 1


type Builder = Callable[[FloatArray], Primitive]


def direction_of(primitive: Primitive) -> FloatArray | None:
    """The plane normal or the axis of a primitive; None for spheres."""
    match primitive:
        case Plane(normal=normal):
            return np.asarray(normal, dtype=np.float64)
        case Cylinder(axis=axis) | Cone(axis=axis) | Torus(axis=axis):
            return np.asarray(axis, dtype=np.float64)
    return None


def _direction(x: _Vector, start: FloatArray, c: Constraints) -> Callable[[FloatArray], FloatArray]:
    if c.direction is not None:
        fixed = unit(c.direction)
        if fixed @ start < 0:
            fixed = -fixed
        return lambda _: fixed
    if c.perpendicular_to is not None:
        t = unit(c.perpendicular_to)
        b1 = start - (start @ t) * t
        b1 = frame_from_axis(t)[0] if np.linalg.norm(b1) < 1e-6 else unit(b1)
        b2 = np.cross(t, b1)
        i = x.add("direction", 0.0)
        return lambda v: np.cos(v[i]) * b1 + np.sin(v[i]) * b2
    e1, e2 = frame_from_axis(start)
    i, j = x.add("direction", 0.0), x.add("direction", 0.0)
    return lambda v: unit(start + v[i] * e1 + v[j] * e2)


def _scalar(
    x: _Vector, name: str, fixed: float | None, start: float
) -> Callable[[FloatArray], float]:
    if fixed is not None:
        value = float(fixed)
        return lambda _: value
    i = x.add(name, start)
    return lambda v: float(v[i])


def _position(
    x: _Vector, name: str, fixed: FloatArray | None, start: FloatArray
) -> Callable[[FloatArray], FloatArray]:
    if fixed is not None:
        point = np.asarray(fixed, dtype=np.float64)
        return lambda _: point
    idx = [x.add(name, 0.0) for _ in range(3)]
    return lambda v: start + v[idx]


def _model(start: Primitive, c: Constraints) -> tuple[_Vector, Builder]:
    x = _Vector()
    match start:
        case Plane(origin=origin, normal=normal):
            n0 = np.asarray(normal)
            direction = _direction(x, n0, c)
            base = np.asarray(origin)
            if c.point is not None:
                point = np.asarray(c.point)

                def plane_with_point(v: FloatArray) -> Primitive:
                    return Plane(origin=vec3(point), normal=vec3(direction(v)))

                return x, plane_with_point
            offset = _scalar(x, "offset", c.offset, float(base @ n0))

            def plane(v: FloatArray) -> Primitive:
                n = direction(v)
                o = base - (base @ n - offset(v)) * n
                return Plane(origin=vec3(o), normal=vec3(n))

            return x, plane
        case Sphere(center=center, radius=radius):
            centre = _position(x, "center", c.point, np.asarray(center))
            r = _scalar(x, "radius", c.radius, radius)
            return x, lambda v: Sphere(center=vec3(centre(v)), radius=r(v))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            a0 = np.asarray(axis)
            direction = _direction(x, a0, c)
            if c.point is not None:
                point = np.asarray(c.point)

                def through(_: FloatArray) -> FloatArray:
                    return point
            else:
                e1, e2 = frame_from_axis(a0)
                base = np.asarray(origin)
                i, j = x.add("origin", 0.0), x.add("origin", 0.0)

                def through(v: FloatArray) -> FloatArray:
                    result: FloatArray = base + v[i] * e1 + v[j] * e2
                    return result

            r = _scalar(x, "radius", c.radius, radius)
            return x, lambda v: Cylinder(
                origin=vec3(through(v)), axis=vec3(direction(v)), radius=r(v)
            )
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            direction = _direction(x, np.asarray(axis), c)
            tip = _position(x, "apex", c.point, np.asarray(apex))
            angle = _scalar(x, "halfAngle", c.half_angle, half_angle)
            return x, lambda v: Cone(
                apex=vec3(tip(v)), axis=vec3(direction(v)), half_angle=angle(v)
            )
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            direction = _direction(x, np.asarray(axis), c)
            centre = _position(x, "center", c.point, np.asarray(center))
            big = _scalar(x, "majorRadius", c.major_radius, major)
            small = _scalar(x, "minorRadius", c.minor_radius, minor)
            return x, lambda v: Torus(
                center=vec3(centre(v)),
                axis=vec3(direction(v)),
                major_radius=big(v),
                minor_radius=small(v),
            )
    raise FitError(f"unsupported primitive {start}")


def _jacobian(
    build: Builder, x: FloatArray, points: FloatArray, base: FloatArray, step: float = 1e-6
) -> FloatArray:
    columns = []
    for k in range(len(x)):
        shifted = x.copy()
        shifted[k] += step
        columns.append((signed_distance(build(shifted), points) - base) / step)
    return np.column_stack(columns) if columns else np.zeros((len(points), 0))


def _uncertainty(names: list[str], covariance: FloatArray) -> dict[str, float]:
    result: dict[str, float] = {}
    variance = np.diag(covariance) if covariance.size else np.zeros(0)
    direction = [variance[k] for k, name in enumerate(names) if name == "direction"]
    if direction:
        result["direction"] = float(np.degrees(np.sqrt(np.mean(direction))))
    for k, name in enumerate(names):
        if name in ("offset", "radius", "majorRadius", "minorRadius"):
            result[name] = float(np.sqrt(max(variance[k], 0.0)))
        elif name == "halfAngle":
            result[name] = float(np.degrees(np.sqrt(max(variance[k], 0.0))))
    return result


def refine_constrained(
    start: Primitive,
    points: FloatArray,
    constraints: Constraints,
    rng: np.random.Generator,
) -> ConstrainedFit:
    """Refine `start` with the constraints applied; RMS on all points."""
    sample = points
    if len(points) > MAX_REFINE_POINTS:
        sample = points[rng.choice(len(points), MAX_REFINE_POINTS, replace=False)]
    vector, build = _model(start, constraints)
    x0 = np.asarray(vector.start, dtype=np.float64)

    def residual(v: FloatArray) -> FloatArray:
        return signed_distance(build(v), sample)

    if len(x0):
        f_scale = max(robust_sigma(residual(x0)), 1e-3)
        solution = least_squares(
            residual, x0, loss="soft_l1", f_scale=f_scale, method="trf", x_scale="jac"
        )
        x = np.asarray(solution.x, dtype=np.float64)
    else:
        x = x0
    fitted = build(x)
    if not all(np.all(np.isfinite(np.asarray(value))) for value in _values(fitted)):
        raise FitError("constrained fit did not converge")
    base = signed_distance(fitted, sample)
    jacobian = _jacobian(build, x, sample, base)
    sigma = max(robust_sigma(base), 1e-6)
    covariance = np.linalg.pinv(jacobian.T @ jacobian) * sigma**2 if len(x) else np.zeros((0, 0))
    distances = signed_distance(fitted, points)
    return ConstrainedFit(
        primitive=_normalised(fitted, points),
        rms=float(np.sqrt(np.mean(distances * distances))),
        uncertainty=_uncertainty(vector.names, covariance),
    )


def fit_constrained(
    kind: PrimitiveKind,
    points: FloatArray,
    normals: FloatArray,
    constraints: Constraints,
    rng: np.random.Generator,
    start: Primitive | None = None,
) -> ConstrainedFit:
    """Free closed-form fit (unless `start` is given), then the constrained refinement."""
    if start is None:
        start = fit_primitive(kind, points, normals, rng).primitive
    return refine_constrained(start, points, constraints, rng)


def _values(primitive: Primitive) -> list[object]:
    return list(vars(primitive).values())[1:]


def _normalised(primitive: Primitive, points: FloatArray) -> Primitive:
    """Canonical form: plane origin at the centroid projection, cylinder origin mid-extent."""
    match primitive:
        case Plane(origin=origin, normal=normal):
            n = unit(normal)
            centroid = points.mean(axis=0)
            o = centroid - ((centroid - np.asarray(origin)) @ n) * n
            return Plane(origin=vec3(o), normal=vec3(n))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            a = unit(axis)
            o = np.asarray(origin)
            h = (points - o) @ a
            o = o + 0.5 * (h.min() + h.max()) * a
            return Cylinder(origin=vec3(o), axis=vec3(a), radius=abs(radius))
        case Sphere(center=center, radius=radius):
            return Sphere(center=center, radius=abs(radius))
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            return Torus(
                center=center,
                axis=vec3(unit(axis)),
                major_radius=major,
                minor_radius=abs(minor),
            )
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            return Cone(apex=apex, axis=vec3(unit(axis)), half_angle=half_angle)
    return primitive
