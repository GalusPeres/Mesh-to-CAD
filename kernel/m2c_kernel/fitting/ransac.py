"""LO-RANSAC for selections that contain other surfaces or junk.

Hypotheses come from minimal point-normal samples and are scored on a
subsample of at most 20 000 points: a point counts when it lies within `eps` of
the surface and its normal agrees with the surface normal within 25 degrees.
The number of hypotheses adapts to the best inlier ratio found so far. The best
hypothesis is then refined by alternating least-squares refits and consensus on
all points with a threshold that shrinks from 3 eps to eps (local
optimisation), which repairs the poor axis of a noisy minimal sample.
Background: `.work/research/algorithms-mesh.md` 3.4.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.fit import FitError, FitResult, fit_primitive
from m2c_kernel.fitting.primitives import (
    Cone,
    Cylinder,
    Plane,
    Primitive,
    PrimitiveKind,
    Sphere,
    signed_distance,
    surface_normals,
)
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit, vec3

MIN_SAMPLE: dict[PrimitiveKind, int] = {"plane": 3, "sphere": 2, "cylinder": 2, "cone": 3, "torus": 12}
SCORE_POINTS = 20_000
MAX_HYPOTHESES = 3_000
SUCCESS_PROBABILITY = 0.999
NORMAL_ANGLE_DEG = 25.0


@dataclass(frozen=True)
class RansacResult:
    fit: FitResult
    inliers: npt.NDArray[np.bool_]
    hypotheses: int


def _minimal(
    kind: PrimitiveKind, p: FloatArray, n: FloatArray, rng: np.random.Generator
) -> Primitive | None:
    """A primitive from a minimal sample of point-normal pairs, or None if degenerate."""
    if kind == "plane":  # three points: a single noisy normal would tilt the plane
        normal = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(normal) < 1e-9:
            return None
        return Plane(origin=vec3(p[0]), normal=vec3(unit(normal)))
    if kind == "sphere":  # closest points of the two normal lines
        n1, n2 = n[0], n[1]
        system = np.array([[n1 @ n1, -n1 @ n2], [n1 @ n2, -n2 @ n2]])
        if abs(np.linalg.det(system)) < 1e-6:
            return None
        t = np.linalg.solve(system, [(p[1] - p[0]) @ n1, (p[1] - p[0]) @ n2])
        centre = 0.5 * (p[0] + t[0] * n1 + p[1] + t[1] * n2)
        return Sphere(center=vec3(centre), radius=float(np.linalg.norm(p[0] - centre)))
    if kind == "cylinder":  # axis = n1 x n2, centre from the projected normal lines
        axis = np.cross(n[0], n[1])
        if np.linalg.norm(axis) < 0.05:
            return None
        axis = unit(axis)
        e1, e2 = frame_from_axis(axis)
        q1, q2 = np.array([p[0] @ e1, p[0] @ e2]), np.array([p[1] @ e1, p[1] @ e2])
        m1 = unit(np.array([n[0] @ e1, n[0] @ e2]))
        m2 = unit(np.array([n[1] @ e1, n[1] @ e2]))
        system = np.column_stack([m1, -m2])
        if abs(np.linalg.det(system)) < 1e-3:
            return None
        t = np.linalg.solve(system, q2 - q1)
        c = q1 + t[0] * m1
        return Cylinder(origin=vec3(c[0] * e1 + c[1] * e2), axis=vec3(axis), radius=float(abs(t[0])))
    if kind == "cone":  # three tangent planes meet in the apex; n . a is constant
        try:
            apex = np.linalg.solve(n[:3], (n[:3] * p[:3]).sum(axis=1))
        except np.linalg.LinAlgError:
            return None
        axis = np.cross(n[0] - n[1], n[0] - n[2])
        if np.linalg.norm(axis) < 1e-6:
            return None
        axis = unit(axis)
        if ((p[:3] - apex) @ axis).mean() < 0:
            axis = -axis
        s = -(n[:3] @ axis).mean()
        if not 0.02 < abs(s) < 0.98:
            return None
        return Cone(apex=vec3(apex), axis=vec3(axis), half_angle=float(np.arcsin(abs(s))))
    try:
        return fit_primitive(kind, p, n, rng).primitive
    except FitError:
        return None


def consensus(
    primitive: Primitive, points: FloatArray, normals: FloatArray, eps: float, cos_tol: float
) -> npt.NDArray[np.bool_]:
    """Inliers: near the surface and with a normal parallel to the surface normal."""
    distance = signed_distance(primitive, points)
    near = np.nonzero(np.abs(distance) < eps)[0]
    mask = np.zeros(len(points), dtype=bool)
    if len(near):
        gradient = surface_normals(primitive, points[near])
        agree = np.abs(np.einsum("ij,ij->i", gradient, normals[near])) > cos_tol
        mask[near[agree]] = True
    return mask


def ransac(
    kind: PrimitiveKind,
    points: FloatArray,
    normals: FloatArray,
    eps: float,
    rng: np.random.Generator,
    local_steps: int = 3,
) -> RansacResult:
    """Robust fit of one primitive type; raises `FitError` if no hypothesis is found."""
    cos_tol = float(np.cos(np.radians(NORMAL_ANGLE_DEG)))
    need = MIN_SAMPLE[kind]
    if len(points) < need:
        raise FitError("too few points for RANSAC")
    score = rng.choice(len(points), min(len(points), SCORE_POINTS), replace=False)
    ps, ns = points[score], normals[score]
    best: Primitive | None = None
    best_count = 0
    budget = MAX_HYPOTHESES if kind != "torus" else MAX_HYPOTHESES // 20
    iteration = 0
    while iteration < budget:
        iteration += 1
        sample = rng.choice(len(ps), need, replace=False)
        candidate = _minimal(kind, ps[sample], ns[sample], rng)
        if candidate is None:
            continue
        count = int(consensus(candidate, ps, ns, eps, cos_tol).sum())
        if count > best_count:
            best, best_count = candidate, count
            ratio = best_count / len(ps)
            needed = np.log(1 - SUCCESS_PROBABILITY) / np.log1p(-(ratio**need) + 1e-15)
            budget = min(budget, int(np.ceil(needed)))
    if best is None or best_count < need:
        raise FitError("RANSAC found no consistent surface")
    inliers = consensus(best, points, normals, 3 * eps, cos_tol)
    fit: FitResult | None = None
    for scale in [3.0, 2.0, 1.5] + [1.0] * local_steps:
        if inliers.sum() < max(need, 10):
            raise FitError("RANSAC consensus collapsed")
        fit = fit_primitive(kind, points[inliers], normals[inliers], rng)
        updated = consensus(fit.primitive, points, normals, scale * eps, cos_tol)
        if scale == 1.0 and np.array_equal(updated, inliers):
            break
        inliers = updated
    assert fit is not None
    return RansacResult(fit=fit, inliers=inliers, hypotheses=iteration)
