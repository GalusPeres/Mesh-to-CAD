"""Fits with fixed parameters and direction relations, plus parameter uncertainties.

A constrained fit starts from a free fit (or any start primitive) and refines
only the parameters the constraints leave free, with the same soft-L1 loss as
`fit.py`. Directions are free (two local parameters around the start
direction), fixed, or perpendicular to a given vector (one angle).

The standard uncertainty of every free parameter comes from the plain
least-squares Jacobian at the solution, `cov = sigma^2 (J^T J)^-1` with the
robust sigma of the residuals. Uncertainties are reported under the parameter
names of the fit tool: `direction` and `halfAngle` in degrees, `point`,
`offset`, `radius`, `majorRadius` and `minorRadius` in millimetres.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.fitting.fit import MAX_REFINE_POINTS, FitError, robust_sigma
from m2c_kernel.fitting.primitives import (
    Cone,
    Cylinder,
    Plane,
    Primitive,
    Sphere,
    Torus,
    signed_distance,
)
from m2c_kernel.geometry import FloatArray, Vec3, frame_from_axis, unit, vec3

JACOBIAN_STEP = 1e-6


@dataclass(frozen=True, kw_only=True)
class Constraints:
    """Values the fit must keep. Directions are unit vectors in part coordinates.

    `direction` is the plane normal or the axis; `perpendicular_to` forces the
    direction perpendicular to a vector. `point` lies on the plane or on the axis
    (cylinder), or is the apex (cone) or the centre (sphere, torus). `offset` is
    the signed distance of a plane from the part origin along its normal.
    `half_angle` is in radians.
    """

    direction: FloatArray | None = None
    perpendicular_to: FloatArray | None = None
    point: FloatArray | None = None
    radius: float | None = None
    half_angle: float | None = None
    major_radius: float | None = None
    minor_radius: float | None = None
    offset: float | None = None

    @property
    def empty(self) -> bool:
        return all(getattr(self, item.name) is None for item in fields(self))


@dataclass(frozen=True)
class ConstrainedFit:
    """A refined primitive, its RMS over all points and the uncertainty of its free values."""

    primitive: Primitive
    rms: float
    uncertainty: dict[str, float]


type Builder = Callable[[FloatArray], Primitive]


class _Parameters:
    """Free parameters of a model, collected while the model is built."""

    def __init__(self) -> None:
        self.start: list[float] = []
        self.names: list[str] = []

    def add(self, name: str, value: float = 0.0) -> int:
        self.start.append(float(value))
        self.names.append(name)
        return len(self.start) - 1


def direction_of(primitive: Primitive) -> FloatArray | None:
    """The plane normal or the axis of a primitive; None for spheres."""
    match primitive:
        case Plane(normal=normal):
            return np.asarray(normal, dtype=np.float64)
        case Cylinder(axis=axis) | Cone(axis=axis) | Torus(axis=axis):
            return np.asarray(axis, dtype=np.float64)
    return None


def _direction(
    x: _Parameters, start: FloatArray, c: Constraints
) -> Callable[[FloatArray], FloatArray]:
    if c.direction is not None:
        fixed = unit(c.direction)
        if fixed @ start < 0:
            fixed = -fixed
        return lambda _: fixed
    if c.perpendicular_to is not None:
        t = unit(c.perpendicular_to)
        b1 = start - (start @ t) * t
        b1 = frame_from_axis(t)[0] if np.linalg.norm(b1) < 1e-9 else unit(b1)
        b2 = np.cross(t, b1)
        i = x.add("direction")
        return lambda v: np.cos(v[i]) * b1 + np.sin(v[i]) * b2
    e1, e2 = frame_from_axis(start)
    i, j = x.add("direction"), x.add("direction")
    return lambda v: unit(start + v[i] * e1 + v[j] * e2)


def _scalar(
    x: _Parameters, name: str, fixed: float | None, start: float
) -> Callable[[FloatArray], float]:
    if fixed is not None:
        value = float(fixed)
        return lambda _: value
    i = x.add(name, start)
    return lambda v: float(v[i])


def _position(
    x: _Parameters, fixed: FloatArray | None, start: FloatArray
) -> Callable[[FloatArray], FloatArray]:
    if fixed is not None:
        point = np.asarray(fixed, dtype=np.float64)
        return lambda _: point
    index = [x.add("point") for _ in range(3)]
    return lambda v: start + v[index]


def _axis_point(
    x: _Parameters, fixed: FloatArray | None, start: FloatArray, axis: FloatArray
) -> Callable[[FloatArray], FloatArray]:
    """A point on an axis; it moves only across the start axis (along it is a gauge freedom)."""
    if fixed is not None:
        point = np.asarray(fixed, dtype=np.float64)
        return lambda _: point
    e1, e2 = frame_from_axis(axis)
    i, j = x.add("point"), x.add("point")
    return lambda v: start + v[i] * e1 + v[j] * e2


def _plane_model(x: _Parameters, plane: Plane, c: Constraints) -> Builder:
    n0 = np.asarray(plane.normal, dtype=np.float64)
    direction = _direction(x, n0, c)
    if c.point is not None:
        point = np.asarray(c.point, dtype=np.float64)
        return lambda v: Plane(origin=vec3(point), normal=vec3(direction(v)))
    base = np.asarray(plane.origin, dtype=np.float64)
    offset = _scalar(x, "offset", c.offset, float(base @ n0))

    def build(v: FloatArray) -> Primitive:
        n = direction(v)
        origin = base - (base @ n - offset(v)) * n
        return Plane(origin=vec3(origin), normal=vec3(n))

    return build


def _model(start: Primitive, c: Constraints) -> tuple[_Parameters, Builder]:
    x = _Parameters()
    match start:
        case Plane():
            return x, _plane_model(x, start, c)
        case Sphere(center=center, radius=radius):
            centre = _position(x, c.point, np.asarray(center))
            r = _scalar(x, "radius", c.radius, radius)
            return x, lambda v: Sphere(center=vec3(centre(v)), radius=r(v))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            a0 = np.asarray(axis, dtype=np.float64)
            direction = _direction(x, a0, c)
            through = _axis_point(x, c.point, np.asarray(origin), a0)
            r = _scalar(x, "radius", c.radius, radius)
            return x, lambda v: Cylinder(
                origin=vec3(through(v)), axis=vec3(direction(v)), radius=r(v)
            )
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            direction = _direction(x, np.asarray(axis), c)
            tip = _position(x, c.point, np.asarray(apex))
            angle = _scalar(x, "halfAngle", c.half_angle, half_angle)
            return x, lambda v: Cone(
                apex=vec3(tip(v)), axis=vec3(direction(v)), half_angle=angle(v)
            )
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            direction = _direction(x, np.asarray(axis), c)
            centre = _position(x, c.point, np.asarray(center))
            big = _scalar(x, "majorRadius", c.major_radius, major)
            small = _scalar(x, "minorRadius", c.minor_radius, minor)
            return x, lambda v: Torus(
                center=vec3(centre(v)),
                axis=vec3(direction(v)),
                major_radius=big(v),
                minor_radius=small(v),
            )
    raise FitError(f"unsupported primitive {start!r}")


def _uncertainty(
    build: Builder, x: FloatArray, names: list[str], sample: FloatArray
) -> dict[str, float]:
    """Standard uncertainty per parameter name from the least-squares Jacobian at `x`."""
    if not len(x):
        return {}
    base = signed_distance(build(x), sample)
    columns = []
    for k in range(len(x)):
        shifted = x.copy()
        shifted[k] += JACOBIAN_STEP
        columns.append((signed_distance(build(shifted), sample) - base) / JACOBIAN_STEP)
    jacobian = np.column_stack(columns)
    sigma = max(robust_sigma(base), 1e-6)
    variance = np.diag(np.linalg.pinv(jacobian.T @ jacobian)) * sigma**2
    grouped: dict[str, list[float]] = {}
    for name, value in zip(names, variance, strict=True):
        grouped.setdefault(name, []).append(max(float(value), 0.0))
    result: dict[str, float] = {}
    for name, values in grouped.items():
        # Directions and points have several parameters; report their RMS.
        standard = float(np.sqrt(np.mean(values)))
        angular = name in ("direction", "halfAngle")
        result[name] = float(np.degrees(standard)) if angular else standard
    return result


def _sample(points: FloatArray, rng: np.random.Generator, limit: int) -> FloatArray:
    if len(points) <= limit:
        return points
    return points[rng.choice(len(points), limit, replace=False)]


def refine_constrained(
    start: Primitive,
    points: FloatArray,
    constraints: Constraints,
    rng: np.random.Generator,
    *,
    solve: bool = True,
    sample_limit: int = MAX_REFINE_POINTS,
) -> ConstrainedFit:
    """Refine `start` with the constraints applied; the RMS is over all points.

    With `solve=False` the start is taken as the solution (a free fit that is
    already refined) and only its uncertainty is computed.
    """
    sample = _sample(points, rng, sample_limit)
    parameters, build = _model(start, constraints)
    x = np.asarray(parameters.start, dtype=np.float64)
    if solve and len(x):

        def residual(v: FloatArray) -> FloatArray:
            return signed_distance(build(v), sample)

        f_scale = max(robust_sigma(residual(x)), 1e-3)
        solution = least_squares(
            residual, x, loss="soft_l1", f_scale=f_scale, method="trf", x_scale="jac"
        )
        x = np.asarray(solution.x, dtype=np.float64)
    fitted = build(x)
    if not _finite(fitted):
        raise FitError("constrained fit did not converge")
    distances = signed_distance(fitted, points)
    return ConstrainedFit(
        primitive=canonical(fitted, points),
        rms=float(np.sqrt(np.mean(distances * distances))),
        uncertainty=_uncertainty(build, x, parameters.names, sample),
    )


def _finite(primitive: Primitive) -> bool:
    values = [getattr(primitive, item.name) for item in fields(primitive) if item.name != "type"]
    return all(np.all(np.isfinite(np.asarray(value, dtype=np.float64))) for value in values)


def canonical(primitive: Primitive, points: FloatArray) -> Primitive:
    """Canonical form: unit directions, positive radii, points placed near the data.

    The plane origin is the projection of the centroid and the cylinder origin
    the middle of the covered extent. Cylinder and torus axes have no natural
    sign; their largest component is made positive. Displayed and stored values
    are therefore stable between fits.
    """
    match primitive:
        case Plane(origin=origin, normal=normal):
            n = unit(normal)
            centroid = points.mean(axis=0)
            o = centroid - ((centroid - np.asarray(origin)) @ n) * n
            return Plane(origin=vec3(o), normal=vec3(n))
        case Cylinder(origin=origin, axis=axis, radius=radius):
            a = _positive(axis)
            o = np.asarray(origin, dtype=np.float64)
            h = (points - o) @ a
            o = o + 0.5 * (h.min() + h.max()) * a
            return Cylinder(origin=vec3(o), axis=vec3(a), radius=abs(radius))
        case Sphere(center=center, radius=radius):
            return Sphere(center=center, radius=abs(radius))
        case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
            return Torus(
                center=center,
                axis=vec3(_positive(axis)),
                major_radius=major,
                minor_radius=abs(minor),
            )
        case Cone(apex=apex, axis=axis, half_angle=half_angle):
            return Cone(apex=apex, axis=vec3(unit(axis)), half_angle=half_angle)
    return primitive


def _positive(axis: Vec3) -> FloatArray:
    a = unit(axis)
    sign: FloatArray = a if a[np.argmax(np.abs(a))] >= 0 else -a
    return sign
