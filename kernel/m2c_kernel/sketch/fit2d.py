"""2D primitive fits: lines, circles and arcs through section points.

Methods and measurements: `.work/research/algorithms-cad.md` 1.2-1.5. Lines are
total-least-squares fits, circles a hyper fit refined by Gauss-Newton on the
geometric distance. Splitting a polyline into such entities is `split2d`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import scipy.linalg

type FloatArray = npt.NDArray[np.float64]
type Kind = Literal["line", "arc"]


@dataclass(frozen=True)
class LineFit:
    angle: float
    """Normal angle: the line is {p : (cos, sin) . p = offset}."""
    offset: float
    max_error: float
    sse: float


@dataclass(frozen=True)
class CircleFit:
    center: FloatArray
    radius: float
    max_error: float
    sse: float


type Fit = LineFit | CircleFit


@dataclass(frozen=True)
class SegmentOptions:
    tolerance: float = 0.1
    """Largest distance of a section point from its entity in mm."""
    max_radius: float = 1000.0
    """Larger arcs are lines."""
    min_arc_sweep: float = math.radians(8.0)
    min_points: int = 5
    min_entity_length: float = 1.0
    """Shorter entities are treated as rounding of scan corners."""
    refine_window: int = 12


def resample(points: FloatArray, spacing: float, closed: bool) -> FloatArray:
    """Points at equal arc length along a polyline (a closed one without the repeated start)."""
    path = np.vstack([points, points[:1]]) if closed else points
    lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(lengths)])
    count = max(round(s[-1] / spacing), 8)
    t = np.linspace(0.0, s[-1], count, endpoint=not closed)
    return np.column_stack([np.interp(t, s, path[:, 0]), np.interp(t, s, path[:, 1])])


def signed_area(points: FloatArray) -> float:
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_in_polygon(point: FloatArray, polygon: FloatArray) -> bool:
    x, y = float(point[0]), float(point[1])
    xi, yi = polygon[:, 0], polygon[:, 1]
    xj, yj = np.roll(xi, 1), np.roll(yi, 1)
    crosses = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi)
    return bool(np.count_nonzero(crosses) % 2)


def estimate_noise(points: FloatArray, closed: bool = True, window: int = 9) -> float:
    """Robust noise sigma: median RMS residual of local line fits over short windows."""
    n = len(points)
    if n < window:
        return 0.0
    if closed:
        idx = (np.arange(n)[:, None] + np.arange(window)[None, :]) % n
    else:
        idx = np.arange(n - window + 1)[:, None] + np.arange(window)[None, :]
    patches = points[idx] - points[idx].mean(axis=1, keepdims=True)
    smallest = np.linalg.svd(patches, compute_uv=False)[:, -1]
    return float(np.median(smallest / math.sqrt(window)))


def fit_line(points: FloatArray) -> LineFit:
    centroid = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - centroid, full_matrices=False)
    normal = vt[1]
    residual = (points - centroid) @ normal
    return LineFit(
        math.atan2(normal[1], normal[0]),
        float(centroid @ normal),
        float(np.abs(residual).max()),
        float(residual @ residual),
    )


def _hyper_circle(points: FloatArray) -> tuple[FloatArray, float] | None:
    """Hyper fit (Al-Sharadqah and Chernov 2009): algebraic, nearly unbiased on short arcs."""
    centroid = points.mean(axis=0)
    x, y = (points - centroid).T
    z = x * x + y * y
    design = np.column_stack([z, x, y, np.ones_like(x)])
    moments = design.T @ design / len(points)
    constraint = np.array(
        [[8 * z.mean(), 0, 0, 2], [0, 1, 0, 0], [0, 0, 1, 0], [2, 0, 0, 0]], dtype=np.float64
    )
    eigval, eigvec = scipy.linalg.eig(moments, constraint)
    eigval = np.real(eigval)
    candidates = np.where(np.isfinite(eigval) & (eigval > -1e-12))[0]
    if len(candidates) == 0:
        return None
    a, b, c, d = np.real(eigvec[:, candidates[np.argmin(eigval[candidates])]])
    if abs(a) < 1e-12:
        return None
    radius_sq = (b * b + c * c - 4 * a * d) / (4 * a * a)
    if radius_sq <= 0:
        return None
    return np.array([-b / (2 * a), -c / (2 * a)]) + centroid, math.sqrt(radius_sq)


def _refine_circle(
    points: FloatArray, center: FloatArray, radius: float, iterations: int = 15
) -> tuple[FloatArray, float]:
    """Gauss-Newton on the geometric distance |p - c| - r."""
    params = np.array([center[0], center[1], radius], dtype=np.float64)
    for _ in range(iterations):
        delta = points - params[:2]
        rho = np.maximum(np.linalg.norm(delta, axis=1), 1e-12)
        residual = rho - params[2]
        jacobian = np.column_stack([-delta[:, 0] / rho, -delta[:, 1] / rho, -np.ones_like(rho)])
        step, *_ = np.linalg.lstsq(jacobian, -residual, rcond=None)
        params += step
        if np.linalg.norm(step) < 1e-10 * max(1.0, params[2]):
            break
    return params[:2].copy(), float(params[2])


def fit_circle(points: FloatArray) -> CircleFit | None:
    if len(points) < 3:
        return None
    initial = _hyper_circle(points)
    if initial is None:
        return None
    center, radius = _refine_circle(points, *initial)
    residual = np.linalg.norm(points - center, axis=1) - radius
    return CircleFit(center, radius, float(np.abs(residual).max()), float(residual @ residual))


def arc_sweep(points: FloatArray, center: FloatArray) -> float:
    """Signed swept angle (positive = counter-clockwise) along the ordered points."""
    angles = np.unwrap(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    return float(angles[-1] - angles[0])


def fit_kind(points: FloatArray, kind: Kind, opts: SegmentOptions) -> Fit | None:
    if kind == "line":
        return fit_line(points)
    circle = fit_circle(points)
    if circle is None or circle.radius > opts.max_radius:
        return None
    if abs(arc_sweep(points, circle.center)) < opts.min_arc_sweep:
        return None
    return circle


def best_fit(points: FloatArray, opts: SegmentOptions) -> tuple[Kind, Fit] | None:
    """A line if it is within tolerance, otherwise an arc, otherwise None."""
    if len(points) < 2:
        return None
    line = fit_line(points)
    if line.max_error <= opts.tolerance:
        return "line", line
    arc = fit_kind(points, "arc", opts) if len(points) >= opts.min_points else None
    if arc is not None and arc.max_error <= opts.tolerance:
        return "arc", arc
    return None
