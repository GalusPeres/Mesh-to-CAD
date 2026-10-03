"""Outlines of recognised features: which simple 2D shape a closed contour is.

A feature's contour (points along its wall, in the plane frame) is fitted with every
candidate shape by robust least squares on the distance to the shape's boundary:

- circle: centre, radius;
- slot (obround): centre, direction, overall length, width;
- rounded rectangle: centre, direction, width, height, corner radius;
- ring segment (an arm of a ring split by straight gaps, e.g. a direction pad):
  centre, inner and outer radius, the angles of the two gap centre lines, the gap
  width (0 gives radial ends) and the corner radius.

The simplest shape whose boundary distance stays near the scan noise wins; a richer
shape must explain the contour clearly better to be chosen. A contour no shape
explains is kept as a free profile (the sketch fitter turns it into lines and arcs).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
from scipy.optimize import least_squares

from m2c_kernel.geometry import FloatArray

type ShapeKind = Literal["circle", "slot", "roundedRect", "ringSegment", "profile"]

RING_REACH = 3.0
"""A ring arm's outer radius is at most this x the size of its contour."""
ACCEPT_FACTOR = 4.0
"""A shape explains a contour when its RMS is below this x the noise (or the floor)."""
ACCEPT_FLOOR_MM = 0.05
BETTER_FACTOR = 0.6
"""A richer shape is chosen over a simpler one only below this x its RMS."""
TAU = 2.0 * np.pi


@dataclass(frozen=True)
class Outline:
    """A fitted 2D outline in the plane frame (mm, angles in radians).

    Attributes:
        kind: The shape.
        params: Shape parameters (see `PARAMETERS`).
        rms: RMS distance of the contour points to the shape's boundary.
    """

    kind: ShapeKind
    params: tuple[float, ...]
    rms: float

    def named(self) -> dict[str, float]:
        return dict(zip(PARAMETERS[self.kind], self.params, strict=True))

    @property
    def center(self) -> tuple[float, float]:
        return self.params[0], self.params[1]


PARAMETERS: dict[ShapeKind, tuple[str, ...]] = {
    "circle": ("cx", "cy", "radius"),
    "slot": ("cx", "cy", "angle", "length", "width"),
    "roundedRect": ("cx", "cy", "angle", "width", "height", "corner"),
    "ringSegment": ("cx", "cy", "inner", "outer", "start", "sweep", "gap", "corner"),
    "profile": ("cx", "cy"),
}


# Distances ---------------------------------------------------------------------------------


def _rotate(
    points: FloatArray, cx: float, cy: float, angle: float
) -> tuple[FloatArray, FloatArray]:
    """Coordinates of the points in a frame at (cx, cy) turned by `angle`."""
    ca, sa = np.cos(angle), np.sin(angle)
    rx, ry = points[:, 0] - cx, points[:, 1] - cy
    return rx * ca + ry * sa, -rx * sa + ry * ca


def circle_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    cx, cy, radius = np.asarray(params, dtype=np.float64)
    result: FloatArray = np.hypot(points[:, 0] - cx, points[:, 1] - cy) - abs(radius)
    return result


def slot_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    """Signed distance to an obround: a segment of length `length - width`, thickened."""
    cx, cy, angle, length, width = np.asarray(params, dtype=np.float64)
    u, v = _rotate(points, cx, cy, angle)
    radius = abs(width) / 2.0
    half = max(abs(length) / 2.0 - radius, 0.0)
    result: FloatArray = np.hypot(u - np.clip(u, -half, half), v) - radius
    return result


def rounded_rect_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    cx, cy, angle, width, height, corner = np.asarray(params, dtype=np.float64)
    u, v = _rotate(points, cx, cy, angle)
    hw, hh = abs(width) / 2.0, abs(height) / 2.0
    r = min(abs(corner), hw, hh)
    qx, qy = np.abs(u) - (hw - r), np.abs(v) - (hh - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    result: FloatArray = outside + inside - r
    return result


def ring_segment_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    """Signed distance to a ring arm with rounded corners.

    The arm lies between the radii `inner` and `outer` and between two straight gaps
    of width `gap` centred on the lines through the centre at `start` and
    `start + sweep` (sweep below a half turn). The sharp arm is eroded by the corner
    radius and grown back by it.
    """
    cx, cy, inner, outer, start, sweep, gap, corner = np.asarray(params, dtype=np.float64)
    inner, outer = sorted((abs(inner), abs(outer)))
    sweep = float(np.clip(abs(sweep), 1e-3, np.pi - 1e-3))
    r = min(abs(corner), (outer - inner) / 2.0)
    half_gap = abs(gap) / 2.0
    dx, dy = points[:, 0] - cx, points[:, 1] - cy
    radius = np.hypot(dx, dy)
    band = np.maximum(inner + r - radius, radius - (outer - r))
    end = start + sweep
    # Distances into the arm from both gap centre lines (inward normals).
    from_start = -dx * np.sin(start) + dy * np.cos(start)
    from_end = dx * np.sin(end) - dy * np.cos(end)
    sides = np.maximum(half_gap + r - from_start, half_gap + r - from_end)
    # Distance to the eroded arm: exact beyond a corner (sides and arcs meet at nearly
    # right angles), then grown back by the corner radius.
    outside = np.hypot(np.maximum(band, 0.0), np.maximum(sides, 0.0))
    inside = np.minimum(np.maximum(band, sides), 0.0)
    result: FloatArray = outside + inside - r
    return result


DISTANCES: dict[ShapeKind, Callable[[npt.ArrayLike, FloatArray], FloatArray]] = {
    "circle": circle_distance,
    "slot": slot_distance,
    "roundedRect": rounded_rect_distance,
    "ringSegment": ring_segment_distance,
}


# Fits --------------------------------------------------------------------------------------


def _principal(points: FloatArray) -> tuple[FloatArray, float, float, float]:
    """Centre, long-axis angle and extents along the long and short axes."""
    centre = points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov((points - centre).T))
    long_axis = vectors[:, 1]
    angle = float(np.arctan2(long_axis[1], long_axis[0]))
    u, v = _rotate(points, centre[0], centre[1], angle)
    mid = np.array([(u.max() + u.min()) / 2.0, (v.max() + v.min()) / 2.0])
    ca, sa = np.cos(angle), np.sin(angle)
    centre = centre + mid[0] * np.array([ca, sa]) + mid[1] * np.array([-sa, ca])
    return centre, angle, float(np.ptp(u)), float(np.ptp(v))


def _solve(kind: ShapeKind, start: list[float], points: FloatArray, scale: float) -> Outline:
    distance = DISTANCES[kind]
    solution = least_squares(
        lambda p: distance(p, points), start, loss="soft_l1", f_scale=scale, max_nfev=400
    )
    rms = float(np.sqrt(np.mean(distance(solution.x, points) ** 2)))
    return Outline(kind, _normalised(kind, solution.x), rms)


def _normalised(kind: ShapeKind, params: FloatArray) -> tuple[float, ...]:
    p = [float(value) for value in params]
    match kind:
        case "circle":
            p[2] = abs(p[2])
        case "slot":
            p[3], p[4] = abs(p[3]), abs(p[4])
            p[3] = max(p[3], p[4])
            p[2] = float(np.mod(p[2], np.pi))
        case "roundedRect":
            p[3], p[4] = abs(p[3]), abs(p[4])
            if p[4] > p[3]:
                p[3], p[4] = p[4], p[3]
                p[2] += np.pi / 2.0
            p[2] = float(np.mod(p[2], np.pi))
            p[5] = min(abs(p[5]), p[3] / 2.0, p[4] / 2.0)
        case "ringSegment":
            p[2], p[3] = sorted((abs(p[2]), abs(p[3])))
            p[5] = float(np.clip(abs(p[5]), 0.0, np.pi))
            p[4] = float(np.mod(p[4], TAU))
            p[6] = abs(p[6])
            p[7] = min(abs(p[7]), (p[3] - p[2]) / 2.0)
    return tuple(p)


def fit_circle(points: FloatArray, scale: float) -> Outline:
    centre = points.mean(axis=0)
    radius = float(np.hypot(*(points - centre).T).mean())
    return _solve("circle", [centre[0], centre[1], radius], points, scale)


def fit_slot(points: FloatArray, scale: float) -> Outline:
    centre, angle, length, width = _principal(points)
    return _solve("slot", [centre[0], centre[1], angle, length, width], points, scale)


def fit_rounded_rect(points: FloatArray, scale: float) -> Outline:
    centre, angle, length, width = _principal(points)
    corner = min(length, width) / 6.0
    start = [centre[0], centre[1], angle, length, width, corner]
    return _solve("roundedRect", start, points, scale)


def fit_ring_segment(
    points: FloatArray, scale: float, centre: tuple[float, float] | None = None
) -> Outline | None:
    """An annular sector; the centre is found as the centre of the contour's curvature.

    With a known centre (a concentric button, a pattern) only the radii and angles
    are fitted first, then everything is refined.
    """
    if centre is None:
        guess = _ring_centre(points)
        if guess is None:
            return None
        centre = guess
    cx, cy = centre
    radius = np.hypot(points[:, 0] - cx, points[:, 1] - cy)
    angles = np.arctan2(points[:, 1] - cy, points[:, 0] - cx)
    middle = float(np.angle(np.mean(np.exp(1j * angles))))
    offset = np.mod(angles - middle + np.pi, TAU) - np.pi
    sweep = float(np.ptp(offset))
    if not 0.05 < sweep < np.pi - 0.05:
        return None
    inner, outer = float(np.percentile(radius, 5)), float(np.percentile(radius, 95))
    corner = (outer - inner) / 6.0
    best: Outline | None = None
    # Radial ends, and ends along straight gaps (start wider: the gap eats into it).
    for gap, widen in ((0.0, 0.0), (0.2 * (outer - inner), 0.15)):
        start = [cx, cy, inner, outer, middle - sweep / 2 - widen, sweep + 2 * widen, gap, corner]
        fitted = _solve("ringSegment", start, points, scale)
        if not _plausible_ring(fitted, points):
            continue
        if best is None or fitted.rms < best.rms:
            best = fitted
    return best


def _plausible_ring(ring: Outline, points: FloatArray) -> bool:
    """A ring arm around a centre near the contour, not a straight band in disguise.

    On a nearly straight contour the fit can run off to a huge radius and gap.
    """
    p = ring.named()
    size = float(np.ptp(points, axis=0).max())
    width = p["outer"] - p["inner"]
    return bool(
        p["inner"] > 0.0
        and width > 0.0
        and p["outer"] < RING_REACH * size
        and 0.0 <= p["gap"] < p["outer"]
        and 0.05 < p["sweep"] < np.pi
    )


def _ring_centre(points: FloatArray) -> tuple[float, float] | None:
    """Centre of the circle through the contour's most curved side (algebraic fit)."""
    centre, angle, length, _ = _principal(points)
    _, v = _rotate(points, centre[0], centre[1], angle)
    best: tuple[float, float] | None = None
    best_rms = np.inf
    # Candidate arcs: the points on either side of the long axis.
    for side in (v > 0, v < 0):
        chosen = points[side]
        if len(chosen) < 8:
            continue
        a = np.column_stack([chosen, np.ones(len(chosen))])
        b = (chosen**2).sum(axis=1)
        sol = np.linalg.lstsq(a, b, rcond=None)[0]
        cx, cy = sol[0] / 2.0, sol[1] / 2.0
        r = np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
        if not length / 2.0 < r < 50.0 * length:
            continue
        rms = float(np.sqrt(np.mean((np.hypot(chosen[:, 0] - cx, chosen[:, 1] - cy) - r) ** 2)))
        if rms < best_rms:
            best, best_rms = (float(cx), float(cy)), rms
    return best


# Choice --------------------------------------------------------------------------------------


def fit_outline(
    points: FloatArray, noise: float, centre: tuple[float, float] | None = None
) -> Outline:
    """The simplest shape that explains the contour, else a free profile.

    Args:
        points: (n, 2) contour points in the plane frame.
        noise: Scan noise (mm), scales the acceptance threshold.
        centre: A known centre for ring segments (a concentric feature), if any.
    """
    accept = max(ACCEPT_FACTOR * noise, ACCEPT_FLOOR_MM)
    scale = max(noise, 0.01)
    candidates = [
        fit_circle(points, scale),
        fit_slot(points, scale),
        fit_rounded_rect(points, scale),
    ]
    ring = fit_ring_segment(points, scale, centre)
    if ring is not None:
        candidates.append(ring)
    chosen = candidates[0]
    for candidate in candidates[1:]:
        if candidate.rms < BETTER_FACTOR * chosen.rms:
            chosen = candidate
    if chosen.rms > accept:
        centre_xy = points.mean(axis=0)
        return Outline("profile", (float(centre_xy[0]), float(centre_xy[1])), chosen.rms)
    return chosen


def outline_points(outline: Outline, count: int = 256) -> FloatArray:
    """Points on the outline's boundary (for display), found by marching the distance."""
    if outline.kind == "profile":
        return np.zeros((0, 2))
    distance = DISTANCES[outline.kind]
    cx, cy = outline.center
    reach = 4.0 * max(abs(value) for value in outline.params[2:]) + 1.0
    angles = np.linspace(0.0, TAU, count, endpoint=False)
    rays = np.column_stack([np.cos(angles), np.sin(angles)])
    if outline.kind == "ringSegment":
        p = outline.named()
        cx += (p["inner"] + p["outer"]) / 2.0 * np.cos(p["start"] + p["sweep"] / 2.0)
        cy += (p["inner"] + p["outer"]) / 2.0 * np.sin(p["start"] + p["sweep"] / 2.0)
    # Bisection along each ray from the inside point to the boundary.
    low = np.zeros(count)
    high = np.full(count, reach)
    for _ in range(40):
        mid = (low + high) / 2.0
        inside = (
            distance(
                outline.params, np.column_stack([cx + rays[:, 0] * mid, cy + rays[:, 1] * mid])
            )
            < 0
        )
        low = np.where(inside, mid, low)
        high = np.where(inside, high, mid)
    result: FloatArray = np.column_stack([cx + rays[:, 0] * low, cy + rays[:, 1] * low])
    return result
