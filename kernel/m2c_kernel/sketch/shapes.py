"""Which simple shape a closed section outline is: circle, slot, rounded rectangle, ring arm.

Research D.6 step 3 (template recognition of buttons). Every candidate is fitted by
robust least squares on the signed distance to its boundary:

- circle: centre, radius;
- slot (obround): centre, direction, overall length, width;
- rounded rectangle: centre, direction, length, width, corner radius;
- ring arm (an arm of a ring split by straight gaps, such as a direction pad):
  centre, inner and outer radius, start and sweep of the gap centre lines, half
  gap width and corner radius.

The simplest shape whose RMS stays below the accept limit wins; a richer shape must
explain the outline clearly better. An outline no shape explains stays a free profile
(the sketch fitter splits it into lines and arcs). Sizes can be held fixed, so the
shape is refitted with its snapped design values.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import ConvexHull

from m2c_kernel.sketch.fit2d import fit_circle, signed_area
from m2c_kernel.sketch.model import FloatArray
from m2c_kernel.sketch.params import ShapeKind

PARAMETERS: dict[ShapeKind, tuple[str, ...]] = {
    "circle": ("cx", "cy", "radius"),
    "slot": ("cx", "cy", "angle", "length", "width"),
    "roundedRect": ("cx", "cy", "angle", "length", "width", "corner"),
    "ringArm": ("cx", "cy", "inner", "outer", "start", "sweep", "gap", "corner"),
}
"""Shape parameters (mm, angles in radians). `gap` is half the width of a gap."""

ORDER: tuple[ShapeKind, ...] = ("circle", "slot", "roundedRect", "ringArm")
"""Simplest first."""
BETTER_FACTOR = 0.7
"""A richer shape is chosen over a simpler one only below this x its RMS."""
ACCEPT_TOLERANCES = 2.0
"""A shape explains an outline when its RMS is below this many fit tolerances..."""
ACCEPT_SIZE_SHARE = 0.012
"""...or below this share of the outline size (wavy scans of small buttons)."""
RING_REACH = 4.0
"""A ring arm's outer radius is at most this x the size of its outline."""
CANDIDATE_POINTS = 256
"""Candidates are compared on this many points of the outline; the winner uses all."""
CONVEX_SHARE = 0.97
"""Outlines filling more of their convex hull are convex (no ring arm)."""


@dataclass(frozen=True)
class ShapeFit:
    kind: ShapeKind
    values: Mapping[str, float]
    rms: float

    def __getitem__(self, name: str) -> float:
        return self.values[name]

    @property
    def center(self) -> FloatArray:
        return np.array([self.values["cx"], self.values["cy"]])


# --------------------------------------------------------------------------- distances


def _local(points: FloatArray, cx: float, cy: float, angle: float) -> tuple[FloatArray, FloatArray]:
    """Coordinates in a frame at (cx, cy) turned by `angle`."""
    ca, sa = math.cos(angle), math.sin(angle)
    rx, ry = points[:, 0] - cx, points[:, 1] - cy
    return rx * ca + ry * sa, -rx * sa + ry * ca


def _circle(p: Mapping[str, float], points: FloatArray) -> FloatArray:
    result: FloatArray = np.hypot(points[:, 0] - p["cx"], points[:, 1] - p["cy"]) - abs(p["radius"])
    return result


def _slot(p: Mapping[str, float], points: FloatArray) -> FloatArray:
    u, v = _local(points, p["cx"], p["cy"], p["angle"])
    radius = abs(p["width"]) / 2.0
    half = max(abs(p["length"]) / 2.0 - radius, 0.0)
    result: FloatArray = np.hypot(u - np.clip(u, -half, half), v) - radius
    return result


def _rounded_rect(p: Mapping[str, float], points: FloatArray) -> FloatArray:
    u, v = _local(points, p["cx"], p["cy"], p["angle"])
    hl, hw = abs(p["length"]) / 2.0, abs(p["width"]) / 2.0
    r = min(abs(p["corner"]), hl, hw)
    qx, qy = np.abs(u) - (hl - r), np.abs(v) - (hw - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    result: FloatArray = outside + np.minimum(np.maximum(qx, qy), 0.0) - r
    return result


def _ring_arm(p: Mapping[str, float], points: FloatArray) -> FloatArray:
    """Signed distance to a ring arm.

    The arm is the ring between `inner` and `outer`, between two gaps of half width
    `gap` centred on the rays at `start` and `start + sweep`; it is eroded by the
    corner radius and grown back by it.
    """
    inner, outer = sorted((abs(p["inner"]), abs(p["outer"])))
    r = min(abs(p["corner"]), (outer - inner) / 2.0)
    gap = abs(p["gap"])
    dx, dy = points[:, 0] - p["cx"], points[:, 1] - p["cy"]
    rho = np.hypot(dx, dy)
    band = np.maximum(inner + r - rho, rho - (outer - r))
    a0 = p["start"]
    a1 = a0 + float(np.clip(abs(p["sweep"]), 1e-3, math.pi - 1e-3))
    into_start = -dx * math.sin(a0) + dy * math.cos(a0)
    into_end = dx * math.sin(a1) - dy * math.cos(a1)
    sides = np.maximum(gap + r - into_start, gap + r - into_end)
    outside = np.hypot(np.maximum(band, 0.0), np.maximum(sides, 0.0))
    result: FloatArray = outside + np.minimum(np.maximum(band, sides), 0.0) - r
    return result


DISTANCES: dict[ShapeKind, Callable[[Mapping[str, float], FloatArray], FloatArray]] = {
    "circle": _circle,
    "slot": _slot,
    "roundedRect": _rounded_rect,
    "ringArm": _ring_arm,
}


def distances(shape: ShapeFit, points: FloatArray) -> FloatArray:
    """Signed distances of points to the shape's boundary (negative inside)."""
    return DISTANCES[shape.kind](shape.values, points)


# --------------------------------------------------------------------------- fitting


def fit_shape(
    kind: ShapeKind,
    points: FloatArray,
    start: Mapping[str, float],
    scale: float,
    fixed: Mapping[str, float] | None = None,
) -> ShapeFit:
    """Robust least squares from `start`; the parameters in `fixed` keep their values."""
    fixed = fixed or {}
    names = [n for n in PARAMETERS[kind] if n not in fixed]
    distance = DISTANCES[kind]

    def values(x: FloatArray) -> dict[str, float]:
        return {**dict(zip(names, (float(v) for v in x), strict=True)), **fixed}

    solution = least_squares(
        lambda x: distance(values(x), points),
        [start[n] for n in names],
        loss="soft_l1",
        f_scale=scale,
        max_nfev=300,
    )
    fitted = _normalised(kind, values(solution.x))
    rms = float(np.sqrt(np.mean(distance(fitted, points) ** 2)))
    return ShapeFit(kind, fitted, rms)


def _normalised(kind: ShapeKind, p: dict[str, float]) -> dict[str, float]:
    p = dict(p)
    match kind:
        case "circle":
            p["radius"] = abs(p["radius"])
        case "slot":
            p["width"] = abs(p["width"])
            p["length"] = max(abs(p["length"]), p["width"])
            p["angle"] = float(np.mod(p["angle"], math.pi))
        case "roundedRect":
            p["length"], p["width"] = abs(p["length"]), abs(p["width"])
            if p["width"] > p["length"]:
                p["length"], p["width"] = p["width"], p["length"]
                p["angle"] += math.pi / 2.0
            p["angle"] = float(np.mod(p["angle"], math.pi))
            p["corner"] = min(abs(p["corner"]), p["width"] / 2.0)
        case "ringArm":
            p["inner"], p["outer"] = sorted((abs(p["inner"]), abs(p["outer"])))
            p["sweep"] = float(np.clip(abs(p["sweep"]), 0.0, math.pi))
            p["start"] = float(np.mod(p["start"], 2.0 * math.pi))
            p["gap"] = abs(p["gap"])
            p["corner"] = min(abs(p["corner"]), (p["outer"] - p["inner"]) / 2.0)
    return p


def _principal(points: FloatArray) -> tuple[FloatArray, float, float, float]:
    """Centre of the extents, long-axis angle and extents along the long and short axis."""
    centre = points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov((points - centre).T))
    angle = float(math.atan2(vectors[1, 1], vectors[0, 1]))
    u, v = _local(points, float(centre[0]), float(centre[1]), angle)
    mid_u, mid_v = (u.max() + u.min()) / 2.0, (v.max() + v.min()) / 2.0
    ca, sa = math.cos(angle), math.sin(angle)
    centre = centre + mid_u * np.array([ca, sa]) + mid_v * np.array([-sa, ca])
    return centre, angle, float(np.ptp(u)), float(np.ptp(v))


def _starts(kind: ShapeKind, points: FloatArray) -> list[dict[str, float]]:
    centre, angle, length, width = _principal(points)
    cx, cy = float(centre[0]), float(centre[1])
    match kind:
        case "circle":
            circle = fit_circle(points)
            if circle is None:
                return [{"cx": cx, "cy": cy, "radius": (length + width) / 4.0}]
            return [
                {
                    "cx": float(circle.center[0]),
                    "cy": float(circle.center[1]),
                    "radius": circle.radius,
                }
            ]
        case "slot":
            return [{"cx": cx, "cy": cy, "angle": angle, "length": length, "width": width}]
        case "roundedRect":
            base = {"cx": cx, "cy": cy, "angle": angle, "length": length, "width": width}
            return [{**base, "corner": width * share} for share in (0.15, 0.35)]
        case "ringArm":
            return []
    return []


def ring_starts(points: FloatArray, centres: Sequence[FloatArray] = ()) -> list[dict[str, float]]:
    """Start values of a ring arm around each candidate centre.

    The candidates are the centre of the outline's most curved side and the `centres`
    of round entities nearby.
    """
    _, _, length, _ = _principal(points)
    candidates = [*_side_centres(points), *centres]
    starts = []
    for centre in candidates:
        cx, cy = float(centre[0]), float(centre[1])
        rho = np.hypot(points[:, 0] - cx, points[:, 1] - cy)
        if rho.min() < 0.05 * length or rho.max() > RING_REACH * length:
            continue
        angles = np.arctan2(points[:, 1] - cy, points[:, 0] - cx)
        middle = float(np.angle(np.mean(np.exp(1j * angles))))
        offset = np.mod(angles - middle + math.pi, 2.0 * math.pi) - math.pi
        sweep = float(np.ptp(offset))
        if not 0.1 < sweep < math.pi - 0.1:
            continue
        inner, outer = float(np.percentile(rho, 3)), float(np.percentile(rho, 97))
        starts.append(
            {
                "cx": cx,
                "cy": cy,
                "inner": inner,
                "outer": outer,
                "start": middle - sweep / 2.0 - 0.1,
                "sweep": sweep + 0.2,
                "gap": 0.1 * (outer - inner),
                "corner": 0.1 * (outer - inner),
            }
        )
    return starts


def _side_centres(points: FloatArray) -> list[FloatArray]:
    """Centres of circles through either side of the outline's long axis."""
    centre, angle, length, _ = _principal(points)
    _, v = _local(points, float(centre[0]), float(centre[1]), angle)
    result = []
    for side in (v > 0, v < 0):
        circle = fit_circle(points[side]) if np.count_nonzero(side) >= 8 else None
        if circle is not None and length / 2.0 < circle.radius < RING_REACH * length:
            result.append(circle.center)
    return result


def plausible(shape: ShapeFit, points: FloatArray) -> bool:
    """Whether a fit is a real shape.

    Rejected are a ring arm that ran off to a straight band and a slot or rectangle far
    larger than the outline.
    """
    size = float(np.ptp(points, axis=0).max())
    match shape.kind:
        case "ringArm":
            return bool(
                shape["inner"] > 0.0
                and shape["outer"] - shape["inner"] > 0.05 * size
                and shape["outer"] < RING_REACH * size
                and shape["gap"] < shape["outer"]
                and 0.1 < shape["sweep"] < math.pi - 0.05
            )
        case "slot" | "roundedRect":
            return bool(shape["width"] > 0.05 * size and shape["length"] < 2.0 * size)
    return shape["radius"] < size


def candidates(
    points: FloatArray, scale: float, centres: Sequence[FloatArray] = ()
) -> dict[ShapeKind, ShapeFit]:
    """The best plausible fit of every shape kind (ring arms only on concave outlines)."""
    best: dict[ShapeKind, ShapeFit] = {}
    kinds = [k for k in ORDER if k != "ringArm" or not _convex(points)]
    for kind in kinds:
        starts = ring_starts(points, centres) if kind == "ringArm" else _starts(kind, points)
        for start in starts:
            fitted = fit_shape(kind, points, start, scale)
            if not plausible(fitted, points):
                continue
            if kind not in best or fitted.rms < best[kind].rms:
                best[kind] = fitted
    return best


def _convex(points: FloatArray) -> bool:
    hull = ConvexHull(points)
    return abs(signed_area(points)) >= CONVEX_SHARE * float(hull.volume)


def _subsample(points: FloatArray) -> FloatArray:
    if len(points) <= CANDIDATE_POINTS:
        return points
    chosen: FloatArray = points[np.linspace(0, len(points) - 1, CANDIDATE_POINTS).astype(int)]
    return chosen


def accept_limit(points: FloatArray, tolerance: float) -> float:
    size = math.sqrt(abs(signed_area(points)))
    return max(ACCEPT_TOLERANCES * tolerance, ACCEPT_SIZE_SHARE * size)


def choose(
    points: FloatArray,
    tolerance: float,
    centres: Sequence[FloatArray] = (),
    leniency: float = 1.0,
) -> ShapeFit | None:
    """The simplest shape that explains a closed outline, or None for a free profile.

    `points` run once around the outline (not closed); `centres` are centres of round
    entities near it (a ring arm is often concentric with a neighbour). `leniency`
    widens the accept limit (a click asks for a shape).
    """
    scale = max(tolerance / 2.0, 0.01)
    fits = candidates(_subsample(points), scale, centres)
    chosen: ShapeFit | None = None
    for kind in ORDER:
        fitted = fits.get(kind)
        if fitted is None:
            continue
        if chosen is None or fitted.rms < BETTER_FACTOR * chosen.rms:
            chosen = fitted
    if chosen is None:
        return None
    chosen = fit_shape(chosen.kind, points, chosen.values, scale)
    if chosen.rms > leniency * accept_limit(points, tolerance):
        return None
    return chosen
