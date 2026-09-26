"""2D primitive fits and the split of section polylines into lines and arcs.

Methods and measurements: `.work/research/algorithms-cad.md` 1.2-1.5. Lines are
total-least-squares fits, circles a hyper fit refined by Gauss-Newton on the
geometric distance. Closed loops and open chains are split by dynamic
programming with a BIC cost (prefix moments give every candidate fit in O(1)),
breakpoints are refined at sample resolution and slivers are removed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
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


@dataclass
class Segment:
    kind: Kind
    start: int
    end: int
    """Inclusive; shared with the next segment's start."""
    fit: Fit


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


def _turning_angles(points: FloatArray, half_window: int) -> FloatArray:
    ahead = np.roll(points, -half_window, axis=0) - points
    behind = points - np.roll(points, half_window, axis=0)
    cross = behind[:, 0] * ahead[:, 1] - behind[:, 1] * ahead[:, 0]
    angles: FloatArray = np.abs(np.arctan2(cross, np.einsum("ij,ij->i", behind, ahead)))
    return angles


class _PrefixMoments:
    """O(1) line and circle fits for any index range [i, j] of a sample array."""

    def __init__(self, pts: FloatArray) -> None:
        self.center = pts.mean(axis=0)
        self.scale = float(np.sqrt(np.mean(np.sum((pts - self.center) ** 2, axis=1)))) or 1.0
        x, y = ((pts - self.center) / self.scale).T
        z = x * x + y * y
        cols = np.column_stack(
            [np.ones_like(x), x, y, x * x, x * y, y * y, x * z, y * z, z, z * z]
        )
        self.sums = np.vstack([np.zeros(cols.shape[1]), np.cumsum(cols, axis=0)])

    def _moments(self, i: npt.NDArray[np.int64], j: npt.NDArray[np.int64]) -> FloatArray:
        diff: FloatArray = (self.sums[j + 1] - self.sums[i]).T
        return diff

    def line_sse(self, i: npt.NDArray[np.int64], j: npt.NDArray[np.int64]) -> FloatArray:
        n, sx, sy, sxx, sxy, syy, *_ = self._moments(i, j)
        a = sxx - sx * sx / n
        c = syy - sy * sy / n
        b = sxy - sx * sy / n
        smallest = 0.5 * (a + c) - np.sqrt(0.25 * (a - c) ** 2 + b * b)
        result: FloatArray = np.maximum(smallest, 0.0) * self.scale**2
        return result

    def circle_fit(
        self, i: npt.NDArray[np.int64], j: npt.NDArray[np.int64]
    ) -> tuple[FloatArray, FloatArray]:
        """Kasa fit: (geometric SSE estimate, radius) in model units."""
        n, sx, sy, sxx, sxy, syy, sxz, syz, sz, szz = self._moments(i, j)
        m = np.stack(
            [
                np.stack([sxx, sxy, sx], -1),
                np.stack([sxy, syy, sy], -1),
                np.stack([sx, sy, n], -1),
            ],
            -2,
        )
        rhs = -np.stack([sxz, syz, sz], -1)
        m = m + np.eye(3) * 1e-12 * np.trace(m, axis1=-2, axis2=-1)[..., None, None]
        sol = np.linalg.solve(m, rhs[..., None])[..., 0]
        d, e, f = sol[..., 0], sol[..., 1], sol[..., 2]
        radius_sq = np.maximum(0.25 * (d * d + e * e) - f, 1e-30)
        algebraic_sse = np.maximum(szz + np.sum(sol * (-rhs), axis=-1), 0.0)
        return algebraic_sse / (4.0 * radius_sq) * self.scale**2, np.sqrt(radius_sq) * self.scale


def _dp_path(
    pts: FloatArray,
    candidates: npt.NDArray[np.int64],
    sigma: float,
    spacing: float,
    opts: SegmentOptions,
) -> list[tuple[int, int, Kind]]:
    moments = _PrefixMoments(pts)
    a_idx, b_idx = np.triu_indices(len(candidates), k=1)
    i, j = candidates[a_idx], candidates[b_idx]
    count = (j - i + 1).astype(np.float64)
    length = (j - i) * spacing
    line_sse = moments.line_sse(i, j)
    arc_sse, radius = moments.circle_fit(i, j)
    penalty = math.log(len(pts))
    line_cost = line_sse / sigma**2 + 3 * penalty
    arc_cost = arc_sse / sigma**2 + 4 * penalty
    arc_ok = (
        (radius <= opts.max_radius)
        & (length / radius >= opts.min_arc_sweep)
        & (count >= opts.min_points)
    )
    arc_cost = np.where(arc_ok, arc_cost, np.inf)
    too_short = length < opts.min_entity_length
    line_cost[too_short] = np.inf
    arc_cost[too_short] = np.inf
    k = len(candidates)
    cost = np.full((k, k), np.inf)
    use_arc = arc_cost < line_cost
    kind = np.zeros((k, k), dtype=np.int8)
    cost[a_idx, b_idx] = np.where(use_arc, arc_cost, line_cost)
    kind[a_idx, b_idx] = use_arc
    best = np.full(k, np.inf)
    best[0] = 0.0
    back = np.zeros(k, dtype=np.int64)
    for b in range(1, k):
        total = best[:b] + cost[:b, b]
        back[b] = int(np.argmin(total))
        best[b] = total[back[b]]
    path: list[tuple[int, int, Kind]] = []
    b = k - 1
    while b > 0:
        a = int(back[b])
        path.append((int(candidates[a]), int(candidates[b]), "arc" if kind[a, b] else "line"))
        b = a
    return path[::-1]


def _refit(pts: FloatArray, seg: Segment, opts: SegmentOptions) -> None:
    points = pts[seg.start : seg.end + 1]
    fit = fit_kind(points, seg.kind, opts)
    if fit is None:
        seg.kind, fit = "line", fit_line(points)
    seg.fit = fit


def _sse(points: FloatArray, kind: Kind, opts: SegmentOptions) -> float:
    fit = fit_kind(points, kind, opts) if len(points) >= 3 else None
    return math.inf if fit is None else fit.sse


def _refine_breakpoints(pts: FloatArray, segments: list[Segment], opts: SegmentOptions) -> None:
    """Move each shared breakpoint to minimise the summed squared error of both neighbours."""
    for k in range(len(segments) - 1):
        a, b = segments[k], segments[k + 1]
        lo = max(a.start + 2, a.end - opts.refine_window)
        hi = min(b.end - 2, a.end + opts.refine_window)
        best_split, best_cost = a.end, math.inf
        for split in range(lo, hi + 1):
            cost = _sse(pts[a.start : split + 1], a.kind, opts) + _sse(
                pts[split : b.end + 1], b.kind, opts
            )
            if cost < best_cost:
                best_split, best_cost = split, cost
        a.end = b.start = best_split
        _refit(pts, a, opts)
        _refit(pts, b, opts)


def _drop_slivers(pts: FloatArray, segments: list[Segment], opts: SegmentOptions) -> None:
    """Remove slivers (corner rounding of the scan): the neighbours take their points."""
    changed = True
    while changed and len(segments) > 2:
        changed = False
        for k, seg in enumerate(segments):
            span = pts[seg.start : seg.end + 1]
            length = float(np.sum(np.linalg.norm(np.diff(span, axis=0), axis=1)))
            if len(span) >= opts.min_points and length >= opts.min_entity_length:
                continue
            if 0 < k < len(segments) - 1:
                prev, nxt = segments[k - 1], segments[k + 1]
                prev.end = nxt.start = (seg.start + seg.end) // 2
                _refit(pts, prev, opts)
                _refit(pts, nxt, opts)
            elif k == 0:
                segments[1].start = seg.start
                _refit(pts, segments[1], opts)
            else:
                segments[-2].end = seg.end
                _refit(pts, segments[-2], opts)
            segments.pop(k)
            changed = True
            break


def split_polyline(
    samples: FloatArray,
    closed: bool,
    sigma: float,
    spacing: float,
    opts: SegmentOptions,
    max_candidates: int = 400,
) -> tuple[FloatArray, list[Segment]]:
    """Globally optimal (BIC) split of a uniformly sampled polyline into lines and arcs.

    Returns the sample array the segment indices refer to; for closed loops it is
    rotated and closed (last point == first point). Closed loops take two passes: the
    first starts at the sharpest corner, the second at the first-pass breakpoint with
    the largest tangent change, which is a real junction even on smooth loops.
    """
    start = int(np.argmax(_turning_angles(samples, 3))) if closed else 0
    passes = 2 if closed else 1
    pts = samples
    path: list[tuple[int, int, Kind]] = []
    stride = 1
    for _ in range(passes):
        if closed:
            rotated = np.roll(samples, -start, axis=0)
            pts = np.vstack([rotated, rotated[:1]])
        n = len(pts) - 1
        stride = max(1, math.ceil(n / max_candidates))
        candidates = np.unique(np.append(np.arange(0, n, stride), n))
        path = _dp_path(pts, candidates, sigma, spacing, opts)
        if not closed or len(path) < 2:
            break
        breaks = np.array([p[0] for p in path[1:]])
        turn = _turning_angles(pts[:-1], max(3, stride))[breaks]
        new_start = (start + int(breaks[np.argmax(turn)])) % len(samples)
        if new_start == start:
            break
        start = new_start
    segments = [Segment(kind, i, j, fit_line(pts[i : j + 1])) for i, j, kind in path]
    for seg in segments:
        _refit(pts, seg, opts)
    _refine_breakpoints(pts, segments, replace(opts, refine_window=max(opts.refine_window, stride)))
    _drop_slivers(pts, segments, opts)
    _merge_lines(pts, segments, closed, opts)
    return pts, segments


def _merge_lines(pts: FloatArray, segments: list[Segment], closed: bool, opts: SegmentOptions) -> None:
    """Merge neighbouring lines while their union is one line within tolerance."""
    k = 0
    while k < len(segments) - 1:
        a, b = segments[k], segments[k + 1]
        if a.kind == b.kind == "line":
            union = fit_line(pts[a.start : b.end + 1])
            if union.max_error <= opts.tolerance:
                a.end, a.fit = b.end, union
                segments.pop(k + 1)
                continue
        k += 1
    if closed and len(segments) > 2 and segments[0].kind == segments[-1].kind == "line":
        first, last = segments[0], segments[-1]
        n = len(pts) - 1
        union = fit_line(np.vstack([pts[last.start : n], pts[: first.end + 1]]))
        if union.max_error <= opts.tolerance:
            shift = last.start
            rotated = np.roll(pts[:n], -shift, axis=0)
            pts[:] = np.vstack([rotated, rotated[:1]])
            for seg in segments[1:-1]:
                seg.start -= shift - n if seg.start < shift else 0
                seg.start, seg.end = (seg.start + n - shift) % n, (seg.end + n - shift) % n or n
            segments[0] = Segment("line", 0, first.end + n - shift, union)
            segments.pop()
