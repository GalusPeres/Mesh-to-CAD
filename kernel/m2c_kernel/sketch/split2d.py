"""Split of section polylines into lines and arcs.

Methods and measurements: `.work/research/algorithms-cad.md` 1.2-1.5. Closed loops
and open chains are split by dynamic programming with a BIC cost (prefix moments give
every candidate fit in O(1)), breakpoints are refined at sample resolution, slivers are
removed and neighbours one entity explains are merged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from m2c_kernel.sketch.fit2d import (
    Fit,
    FloatArray,
    Kind,
    LineFit,
    SegmentOptions,
    fit_kind,
    fit_line,
)


@dataclass
class Segment:
    kind: Kind
    start: int
    end: int
    """Inclusive; shared with the next segment's start."""
    fit: Fit


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
        cols = np.column_stack([np.ones_like(x), x, y, x * x, x * y, y * y, x * z, y * z, z, z * z])
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


def _range_sse(
    moments: _PrefixMoments, kind: Kind, i: npt.NDArray[np.int64], j: npt.NDArray[np.int64]
) -> FloatArray:
    """Squared errors of fits over the index ranges [i, j] (circles: Kasa estimate)."""
    return moments.line_sse(i, j) if kind == "line" else moments.circle_fit(i, j)[0]


def _refine_breakpoints(pts: FloatArray, segments: list[Segment], opts: SegmentOptions) -> None:
    """Move each shared breakpoint to minimise the summed squared error of both neighbours."""
    moments = _PrefixMoments(pts)
    for k in range(len(segments) - 1):
        a, b = segments[k], segments[k + 1]
        lo = max(a.start + 2, a.end - opts.refine_window)
        hi = min(b.end - 2, a.end + opts.refine_window)
        if hi < lo:
            continue
        splits = np.arange(lo, hi + 1)
        starts = np.full_like(splits, a.start)
        ends = np.full_like(splits, b.end)
        cost = _range_sse(moments, a.kind, starts, splits) + _range_sse(
            moments, b.kind, splits, ends
        )
        a.end = b.start = int(splits[int(np.argmin(cost))])
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
    _merge_neighbours(pts, segments, opts)
    if closed and len(segments) > 2:
        pts, segments = _merge_across_start(pts, segments, opts)
    return pts, segments


def _inner_error(points: FloatArray, fit: Fit, opts: SegmentOptions) -> float:
    """Largest distance from the fit, leaving out the corner rounding at both ends.

    The samples within `min_entity_length` of either end round off the scan's corners
    into the neighbours; they must not keep two pieces of one straight side apart.
    """
    if isinstance(fit, LineFit):
        normal = np.array([math.cos(fit.angle), math.sin(fit.angle)])
        residual = np.abs(points @ normal - fit.offset)
    else:
        residual = np.abs(np.linalg.norm(points - fit.center, axis=1) - fit.radius)
    along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])
    inner = (along > opts.min_entity_length) & (along < along[-1] - opts.min_entity_length)
    return float(residual[inner].max() if inner.any() else residual.max())


def _union_fit(
    points: FloatArray, a: Segment, b: Segment, opts: SegmentOptions
) -> tuple[Kind, Fit] | None:
    """One entity through the points of two neighbours, if it stays within tolerance."""
    line = fit_line(points)
    if _inner_error(points, line, opts) <= opts.tolerance:
        return "line", line
    if a.kind == b.kind == "arc":
        arc = fit_kind(points, "arc", opts)
        if arc is not None and _inner_error(points, arc, opts) <= opts.tolerance:
            return "arc", arc
    return None


def _merge_neighbours(pts: FloatArray, segments: list[Segment], opts: SegmentOptions) -> None:
    """Merge neighbours while one entity describes both within tolerance (spurious splits)."""
    k = 0
    while k < len(segments) - 1 and len(segments) > 1:
        a, b = segments[k], segments[k + 1]
        union = _union_fit(pts[a.start : b.end + 1], a, b, opts)
        if union is None:
            k += 1
            continue
        a.kind, a.fit, a.end = union[0], union[1], b.end
        segments.pop(k + 1)


def _merge_across_start(
    pts: FloatArray, segments: list[Segment], opts: SegmentOptions
) -> tuple[FloatArray, list[Segment]]:
    """On closed loops, merge the last and the first entity if one entity fits both.

    The sample array is rotated so that the merged entity starts at index 0.
    """
    n = len(pts) - 1
    first, last = segments[0], segments[-1]
    joined = np.vstack([pts[last.start : n], pts[: first.end + 1]])
    union = _union_fit(joined, last, first, opts)
    if union is None:
        return pts, segments
    shift = last.start
    rotated = np.roll(pts[:n], -shift, axis=0)
    rotated = np.vstack([rotated, rotated[:1]])
    moved = n - shift
    merged = Segment(union[0], 0, first.end + moved, union[1])
    middle = [Segment(s.kind, s.start + moved, s.end + moved, s.fit) for s in segments[1:-1]]
    return rotated, [merged, *middle]
