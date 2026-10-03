"""Outlines of recognised features: a chain of lines and arcs, named by a template.

A feature's contour (points along its wall, in the plane frame) is fitted with every
template shape (`shapes.py`) by robust least squares on the distance to the shape's
boundary. The simplest template whose boundary distance stays near the scan noise
names the outline; a richer one must explain the contour clearly better to be
chosen. The template carries the design intent (equal sizes, shared centres, round
values; `intent.py`) and gives the chain the sketch is built from (`templates.py`).

A contour no template explains is a free profile: the section sketch's fitter splits
it into lines and arcs (`chain.py`), which is built just the same.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.chain import Chain, chain_distances, chain_size, free_chain
from m2c_kernel.recognition.shapes import (
    DISTANCES,
    PARAMETERS,
    TAU,
    ShapeKind,
    Template,
    rotate,
)
from m2c_kernel.recognition.templates import template_chain
from m2c_kernel.sketch import fit2d, split2d
from m2c_kernel.sketch.noise import sample_spacing, suggested_tolerance

RING_REACH = 3.0
"""A ring arm's outer radius is at most this x the size of its contour."""
ACCEPT_FACTOR = 4.0
"""A shape explains a contour when its RMS is below this x the noise (or the floor)."""
ACCEPT_FLOOR_MM = 0.05
BETTER_FACTOR = 0.6
"""A richer shape is chosen over a simpler one only below this x its RMS."""
CUT_REACH = 0.95
"""A cut closer to the circle's edge than this x the radius leaves a full circle."""


@dataclass(frozen=True)
class Outline:
    """A fitted 2D outline in the plane frame (mm, angles in radians).

    Attributes:
        kind: The template, or "profile" for a free chain of lines and arcs.
        params: Shape parameters (see `PARAMETERS`).
        rms: RMS distance of the contour points to the outline.
        free: The lines and arcs of a free profile.
    """

    kind: ShapeKind
    params: tuple[float, ...]
    rms: float
    free: Chain | None = None

    def named(self) -> dict[str, float]:
        return dict(zip(PARAMETERS[self.kind], self.params, strict=True))

    @property
    def center(self) -> tuple[float, float]:
        return self.params[0], self.params[1]

    @property
    def chain(self) -> Chain:
        """The lines and arcs of the outline (a template's follow from its parameters)."""
        kind = self.kind
        if kind == "profile":
            assert self.free is not None
            return self.free
        return template_chain(kind, self.named())


# Fits --------------------------------------------------------------------------------------


def _principal(points: FloatArray) -> tuple[FloatArray, float, float, float]:
    """Centre, long-axis angle and extents along the long and short axes."""
    centre = points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov((points - centre).T))
    long_axis = vectors[:, 1]
    angle = float(np.arctan2(long_axis[1], long_axis[0]))
    u, v = rotate(points, centre[0], centre[1], angle)
    mid = np.array([(u.max() + u.min()) / 2.0, (v.max() + v.min()) / 2.0])
    ca, sa = np.cos(angle), np.sin(angle)
    centre = centre + mid[0] * np.array([ca, sa]) + mid[1] * np.array([-sa, ca])
    return centre, angle, float(np.ptp(u)), float(np.ptp(v))


def _solve(kind: Template, start: list[float], points: FloatArray, scale: float) -> Outline:
    distance = DISTANCES[kind]
    solution = least_squares(
        lambda p: distance(p, points), start, loss="soft_l1", f_scale=scale, max_nfev=400
    )
    rms = float(np.sqrt(np.mean(distance(solution.x, points) ** 2)))
    return Outline(kind, _normalised(kind, solution.x), rms)


def _normalised(kind: Template, params: FloatArray) -> tuple[float, ...]:
    p = [float(value) for value in params]
    match kind:
        case "circle":
            p[2] = abs(p[2])
        case "cutCircle":
            p[2] = abs(p[2])
            p[3] = float(np.mod(p[3], TAU))
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


def fit_cut_circle(points: FloatArray, scale: float, tolerance: float) -> Outline | None:
    """A circle trimmed by a line; None when the contour has no long arc and straight run.

    A circle fit pulls towards the cut, so the fit starts from the contour's split into
    lines and arcs: its widest arc gives the circle, its longest line the cut.
    """
    spacing = sample_spacing(points, closed=True)
    samples = fit2d.resample(points, spacing, closed=True)
    options = fit2d.SegmentOptions(tolerance=tolerance)
    split, segments = split2d.split_polyline(samples, True, tolerance / 3.0, spacing, options)
    arcs = [s for s in segments if isinstance(s.fit, fit2d.CircleFit)]
    lines = [s for s in segments if isinstance(s.fit, fit2d.LineFit)]
    if not arcs or not lines:
        return None
    arc = max(arcs, key=lambda s: s.end - s.start)
    line = max(lines, key=lambda s: s.end - s.start)
    assert isinstance(arc.fit, fit2d.CircleFit) and isinstance(line.fit, fit2d.LineFit)
    centre, radius = arc.fit.center, arc.fit.radius
    normal = np.array([np.cos(line.fit.angle), np.sin(line.fit.angle)])
    offset = line.fit.offset
    # The cut's normal points away from the arc.
    if normal @ split[(arc.start + arc.end) // 2] > offset:
        normal, offset = -normal, -offset
    angle = float(np.arctan2(normal[1], normal[0]))
    start = [centre[0], centre[1], radius, angle, offset - float(normal @ centre)]
    fitted = _solve("cutCircle", start, points, scale)
    p = fitted.named()
    if not abs(p["cut"]) < CUT_REACH * p["radius"]:
        return None
    return fitted


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
    _, v = rotate(points, centre[0], centre[1], angle)
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
    """The simplest template that explains the contour, else a free chain of lines and arcs.

    Args:
        points: (n, 2) contour points in the plane frame.
        noise: Scan noise (mm), scales the acceptance threshold and the chain's tolerance.
        centre: A known centre for ring segments (a concentric feature), if any.
    """
    accept = max(ACCEPT_FACTOR * noise, ACCEPT_FLOOR_MM)
    scale = max(noise, 0.01)
    circle = fit_circle(points, scale)
    candidates = [
        circle,
        fit_cut_circle(points, scale, suggested_tolerance(noise)),
        fit_slot(points, scale),
        fit_rounded_rect(points, scale),
        fit_ring_segment(points, scale, centre),
    ]
    chosen = circle
    for candidate in candidates[1:]:
        if candidate is not None and candidate.rms < BETTER_FACTOR * chosen.rms:
            chosen = candidate
    if chosen.rms <= accept:
        return chosen
    return free_outline(points, noise)


def free_outline(points: FloatArray, noise: float) -> Outline:
    """A free profile: the contour as lines and arcs within the fit tolerance of the noise."""
    chain = free_chain(points, suggested_tolerance(noise))
    rms = float(np.sqrt(np.mean(chain_distances(chain, points) ** 2)))
    return Outline("profile", chain_size(chain), rms, chain)
