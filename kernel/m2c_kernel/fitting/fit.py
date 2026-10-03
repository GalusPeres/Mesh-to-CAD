"""Least-squares fitting of primitives to scan points.

Each fit starts from a closed-form estimate and is refined with
`scipy.optimize.least_squares(loss="soft_l1")` on at most 30 000 points;
statistics are computed on all points afterwards. Axis directions are
parameterised locally around the start axis (`normalize(a0 + u e1 + v e2)`),
which has no singularities. Background and measurements:
`.work/research/algorithms-mesh.md` section 3 (not part of the repository).

Robust fitting with outliers (RANSAC) and constrained refits live in
`ransac.py` and `constrained.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.optimize import least_squares

from m2c_kernel.fitting.primitives import (
    PRIMITIVE_KINDS,
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

MAX_REFINE_POINTS = 30_000
TRIAL_POINTS = 4_000
TYPE_PENALTY = 1.15
DEGENERATE_RADIUS_RATIO = 20.0
"""A curved fit whose radius exceeds this multiple of the selection size is a flat surface."""
"""A type with more parameters must lower the robust sigma by this factor to win."""

MIN_CONE_HALF_ANGLE = np.radians(0.5)
"""Flatter cones are cylinders for any practical part; their apex is ill-defined."""


class FitError(ValueError):
    """The points do not determine the requested primitive (degenerate input)."""


@dataclass(frozen=True)
class FitResult:
    """A fitted primitive with its quality measures (all distances in mm).

    Attributes:
        primitive: The fitted surface.
        rms: Root mean square of the signed distances of all points.
        max_abs: Largest absolute distance.
        sigma: Robust standard deviation (1.4826 x MAD); ignores outliers.
        inlier_ratio: Share of points within `3 sigma` (or the given tolerance).
        point_count: Number of points used for the statistics.
        concave: For cylinders and spheres: True for a hole, False for a boss.
        length: For cylinders: extent of the points along the axis.
    """

    primitive: Primitive
    rms: float
    max_abs: float
    sigma: float
    inlier_ratio: float
    point_count: int
    concave: bool | None = None
    length: float | None = None
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def kind(self) -> PrimitiveKind:
        return self.primitive.type


def robust_sigma(residuals: npt.ArrayLike) -> float:
    """1.4826 x median absolute deviation: the noise level, insensitive to outliers."""
    r = np.asarray(residuals, dtype=np.float64)
    return float(1.4826 * np.median(np.abs(r - np.median(r))))


def statistics(
    primitive: Primitive,
    points: FloatArray,
    tolerance: float | None = None,
    concave: bool | None = None,
    length: float | None = None,
) -> FitResult:
    """Quality measures of a primitive against all points."""
    d = signed_distance(primitive, points)
    sigma = robust_sigma(d)
    limit = 3.0 * max(sigma, 1e-4) if tolerance is None else tolerance
    return FitResult(
        primitive=primitive,
        rms=float(np.sqrt(np.mean(d * d))),
        max_abs=float(np.abs(d).max()),
        sigma=sigma,
        inlier_ratio=float(np.mean(np.abs(d) <= limit)),
        point_count=len(points),
        concave=concave,
        length=length,
    )


def _plane_pca(points: FloatArray) -> tuple[FloatArray, FloatArray]:
    centroid = points.mean(axis=0)
    centred = points - centroid
    _, vectors = np.linalg.eigh(centred.T @ centred)
    return centroid, vectors[:, 0]


def circle_2d(x: FloatArray, y: FloatArray) -> tuple[float, float, float]:
    """Algebraic (Kasa) circle fit: centre and radius, a start value for refinement."""
    design = np.column_stack([x, y, np.ones_like(x)])
    solution, *_ = np.linalg.lstsq(design, x * x + y * y, rcond=None)
    cx, cy = solution[0] / 2, solution[1] / 2
    return float(cx), float(cy), float(np.sqrt(max(solution[2] + cx * cx + cy * cy, 0.0)))


def _sphere_algebraic(points: FloatArray) -> tuple[FloatArray, float]:
    design = np.column_stack([2 * points, np.ones(len(points))])
    solution, *_ = np.linalg.lstsq(design, (points * points).sum(axis=1), rcond=None)
    centre = solution[:3]
    return centre, float(np.sqrt(max(solution[3] + centre @ centre, 0.0)))


def _cylinder_axis_from_normals(normals: FloatArray) -> FloatArray:
    """Cylinder normals are perpendicular to the axis: smallest eigenvector of their scatter."""
    _, vectors = np.linalg.eigh(normals.T @ normals)
    return vectors[:, 0]


def axis_of_revolution(points: FloatArray, normals: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Axis of a surface of revolution from point-normal pairs (Pottmann and Wallner).

    Every normal line of a surface of revolution meets the axis. In Pluecker
    coordinates the condition is linear in the axis `(a, m)`, so the smallest
    right singular vector of `[p x n, n]` solves it. Returns the axis point
    nearest the centroid and the unit direction.
    """
    centroid = points.mean(axis=0)
    scale = float(np.sqrt(((points - centroid) ** 2).sum(axis=1).mean()))
    q = (points - centroid) / scale
    system = np.column_stack([np.cross(q, normals), normals])
    _, _, vt = np.linalg.svd(system.T @ system)
    a, m = vt[-1][:3], vt[-1][3:]
    length = np.linalg.norm(a)
    if length < 1e-9:
        raise FitError("points do not describe a surface of revolution")
    a, m = a / length, m / length
    m = m - (m @ a) * a
    return np.cross(a, m) * scale + centroid, a


def _profile(
    points: FloatArray, origin: FloatArray, axis: FloatArray
) -> tuple[FloatArray, FloatArray]:
    relative = points - origin
    h = relative @ axis
    rho = np.sqrt(np.maximum((relative * relative).sum(axis=1) - h * h, 0.0))
    return h, rho


def _direction(a0: FloatArray, e1: FloatArray, e2: FloatArray, u: float, v: float) -> FloatArray:
    return unit(a0 + u * e1 + v * e2)


def _refine(
    residual: Callable[[FloatArray, FloatArray], FloatArray],
    x0: FloatArray,
    points: FloatArray,
    rng: np.random.Generator,
) -> FloatArray:
    """Robust (soft-L1) refinement on a random subsample of at most 30 000 points."""
    if len(points) > MAX_REFINE_POINTS:
        points = points[rng.choice(len(points), MAX_REFINE_POINTS, replace=False)]
    f_scale = max(robust_sigma(residual(x0, points)), 1e-3)
    result = least_squares(
        residual, x0, args=(points,), loss="soft_l1", f_scale=f_scale, method="trf", x_scale="jac"
    )
    refined: FloatArray = result.x
    return refined


def fit_plane(
    points: FloatArray, normals: FloatArray | None, rng: np.random.Generator
) -> FitResult:
    centroid, n = _plane_pca(points)
    if normals is not None and (normals @ n).sum() < 0:
        n = -n
    e1, e2 = frame_from_axis(n)

    def residual(x: FloatArray, q: FloatArray) -> FloatArray:
        result: FloatArray = (q - centroid) @ _direction(n, e1, e2, x[0], x[1]) - x[2]
        return result

    x = _refine(residual, np.zeros(3), points, rng)
    normal = _direction(n, e1, e2, x[0], x[1])
    origin = centroid + x[2] * normal
    offset = points.mean(axis=0) - origin
    origin = origin + offset - (offset @ normal) * normal
    return statistics(Plane(origin=vec3(origin), normal=vec3(normal)), points)


def fit_sphere(
    points: FloatArray, normals: FloatArray | None, rng: np.random.Generator
) -> FitResult:
    centre, radius = _sphere_algebraic(points)

    def residual(x: FloatArray, q: FloatArray) -> FloatArray:
        result: FloatArray = np.linalg.norm(q - x[:3], axis=1) - x[3]
        return result

    x = _refine(residual, np.r_[centre, radius], points, rng)
    centre, radius = x[:3], float(x[3])
    concave = None
    if normals is not None:
        concave = bool(np.mean(np.einsum("ij,ij->i", normals, points - centre)) < 0)
    return statistics(Sphere(center=vec3(centre), radius=radius), points, concave=concave)


def fit_cylinder(points: FloatArray, normals: FloatArray, rng: np.random.Generator) -> FitResult:
    a = _cylinder_axis_from_normals(normals)
    e1, e2 = frame_from_axis(a)
    c0 = points.mean(axis=0)
    cx, cy, r = circle_2d((points - c0) @ e1, (points - c0) @ e2)
    origin = c0 + cx * e1 + cy * e2

    def residual(x: FloatArray, q: FloatArray) -> FloatArray:
        axis = _direction(a, e1, e2, x[0], x[1])
        _, rho = _profile(q, origin + x[2] * e1 + x[3] * e2, axis)
        result: FloatArray = rho - x[4]
        return result

    x = _refine(residual, np.array([0.0, 0.0, 0.0, 0.0, r]), points, rng)
    axis = _direction(a, e1, e2, x[0], x[1])
    origin = origin + x[2] * e1 + x[3] * e2
    origin = origin + ((points.mean(axis=0) - origin) @ axis) * axis
    h, _ = _profile(points, origin, axis)
    radial = (points - origin) - np.outer((points - origin) @ axis, axis)
    concave = bool(np.mean(np.einsum("ij,ij->i", normals, radial)) < 0)
    primitive = Cylinder(origin=vec3(origin), axis=vec3(axis), radius=float(x[4]))
    return statistics(primitive, points, concave=concave, length=float(np.ptp(h)))


def fit_cone(points: FloatArray, normals: FloatArray, rng: np.random.Generator) -> FitResult:
    q, a = axis_of_revolution(points, normals)
    h, rho = _profile(points, q, a)
    slope, intercept = np.polyfit(h, rho, 1)
    if slope < 0:
        a, h, slope = -a, -h, -slope
    half_angle = float(np.arctan(slope))
    if half_angle < MIN_CONE_HALF_ANGLE or half_angle > np.pi / 2 - MIN_CONE_HALF_ANGLE:
        raise FitError("cone degenerates to a cylinder or a plane")
    apex = q + a * (-intercept / slope)
    e1, e2 = frame_from_axis(a)

    def residual(x: FloatArray, pts: FloatArray) -> FloatArray:
        axis = _direction(a, e1, e2, x[0], x[1])
        hh, rr = _profile(pts, apex + x[2:5], axis)
        result: FloatArray = rr * np.cos(x[5]) - hh * np.sin(x[5])
        return result

    x = _refine(residual, np.array([0.0, 0.0, 0.0, 0.0, 0.0, half_angle]), points, rng)
    if not MIN_CONE_HALF_ANGLE <= abs(x[5]) <= np.pi / 2 - MIN_CONE_HALF_ANGLE:
        raise FitError("cone degenerates to a cylinder or a plane")
    axis = _direction(a, e1, e2, x[0], x[1])
    primitive = Cone(apex=vec3(apex + x[2:5]), axis=vec3(axis), half_angle=float(x[5]))
    return statistics(primitive, points)


def fit_torus(points: FloatArray, normals: FloatArray, rng: np.random.Generator) -> FitResult:
    q, a = axis_of_revolution(points, normals)
    h, rho = _profile(points, q, a)
    hc, major, minor = circle_2d(h, rho)
    centre = q + hc * a
    e1, e2 = frame_from_axis(a)

    def residual(x: FloatArray, pts: FloatArray) -> FloatArray:
        axis = _direction(a, e1, e2, x[0], x[1])
        hh, rr = _profile(pts, centre + x[2:5], axis)
        result: FloatArray = np.hypot(rr - x[5], hh) - x[6]
        return result

    x0 = np.array([0.0, 0.0, 0.0, 0.0, 0.0, major, minor])
    x = _refine(residual, x0, points, rng)
    axis = _direction(a, e1, e2, x[0], x[1])
    primitive = Torus(
        center=vec3(centre + x[2:5]),
        axis=vec3(axis),
        major_radius=float(x[5]),
        minor_radius=float(abs(x[6])),
    )
    return statistics(primitive, points)


type Fitter = Callable[[FloatArray, FloatArray, np.random.Generator], FitResult]

FITTERS: dict[PrimitiveKind, Fitter] = {
    "plane": fit_plane,
    "sphere": fit_sphere,
    "cylinder": fit_cylinder,
    "cone": fit_cone,
    "torus": fit_torus,
}


def fit_primitive(
    kind: PrimitiveKind, points: FloatArray, normals: FloatArray, rng: np.random.Generator
) -> FitResult:
    """Fit one primitive type. Normals should be jet normals (`mesh.normals.jet_fit`)."""
    try:
        return FITTERS[kind](points, normals, rng)
    except (np.linalg.LinAlgError, ValueError) as error:
        raise FitError(f"{kind} fit failed: {error}") from error


def is_degenerate(primitive: Primitive, extent: float) -> bool:
    """Whether a curved fit is, over a selection of this size, a plane in disguise.

    Almost flat scan regions (a remote control's top, a slightly warped plate) fit a
    sphere or cylinder with a radius of kilometres about as well as a plane; the
    automatic choice must not prefer such a fit.
    """
    limit = DEGENERATE_RADIUS_RATIO * max(extent, 1e-9)
    match primitive:
        case Sphere(radius=radius) | Cylinder(radius=radius):
            return radius > limit
        case Torus(major_radius=major, minor_radius=minor):
            return major > limit or minor > limit
        case Cone(half_angle=half_angle):
            return bool(half_angle > np.radians(89.0))
    return False


def trial_fits(
    points: FloatArray,
    normals: FloatArray,
    rng: np.random.Generator,
    noise: float | None = None,
    kinds: tuple[PrimitiveKind, ...] = PRIMITIVE_KINDS,
) -> tuple[FitResult | None, list[FitResult]]:
    """Trial fits of several types on a subsample, and the preferred one.

    A type with more parameters must lower the robust sigma by `TYPE_PENALTY`
    to be preferred. Plane, sphere and cylinder are always tried; cone and torus
    only when the best simpler fit is clearly above the noise. Returns the
    preferred trial (None if nothing fits) and every successful trial, best first.
    """
    count = min(len(points), TRIAL_POINTS)
    sample = rng.choice(len(points), count, replace=False)
    extent = float(np.linalg.norm(np.ptp(points[sample], axis=0)))
    best: FitResult | None = None
    trials: list[FitResult] = []
    for kind in kinds:
        simple_enough = best is not None and noise is not None and best.sigma < 1.1 * noise
        if kind in ("cone", "torus") and simple_enough:
            continue
        try:
            trial = fit_primitive(kind, points[sample], normals[sample], rng)
        except FitError:
            continue
        if not np.isfinite(trial.sigma):
            continue
        trials.append(trial)
        if is_degenerate(trial.primitive, extent):
            continue
        if best is None or trial.sigma * TYPE_PENALTY < best.sigma:
            best = trial
    trials.sort(key=lambda trial: trial.sigma)
    return best, trials


def fit_best(
    points: FloatArray,
    normals: FloatArray,
    rng: np.random.Generator,
    noise: float | None = None,
    kinds: tuple[PrimitiveKind, ...] = PRIMITIVE_KINDS,
) -> tuple[FitResult, list[FitResult]]:
    """Choose the primitive type automatically (`trial_fits`) and refit it on all points.

    An early exit after the sphere would be wrong: a small patch of a cylinder
    is matched by a sphere almost as well. Returns the winner and the trial fits
    of every type that succeeded, best first (for the alternatives list).
    """
    best, trials = trial_fits(points, normals, rng, noise, kinds)
    if best is None:
        raise FitError("no primitive type fits these points")
    return fit_primitive(best.kind, points, normals, rng), trials
