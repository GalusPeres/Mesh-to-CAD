"""Automatic sketch fit: split, constraints, joint refit, snapping, exact junctions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.sketch import fit2d
from m2c_kernel.sketch.constraints import ConstraintOptions, infer_constraints, solve, update_junctions
from m2c_kernel.sketch.model import Arc, Chain, Circle, Constraint, Entity, FloatArray, Line
from m2c_kernel.sketch.snaps import SnapRecord, find_snaps
from m2c_kernel.snapping import SnapUnits

MIN_TOLERANCE = 0.05
NOISE_FACTOR = 6.0


@dataclass(frozen=True)
class FitOutcome:
    chains: list[Chain]
    constraints: list[Constraint]
    snaps: list[SnapRecord]
    tolerance: float
    noise: float


def suggested_tolerance(noise: float) -> float:
    return max(NOISE_FACTOR * noise, MIN_TOLERANCE)


def _spacing(raw: FloatArray, closed: bool) -> float:
    path = np.vstack([raw, raw[:1]]) if closed else raw
    edges = np.linalg.norm(np.diff(path, axis=0), axis=1)
    return float(np.clip(np.median(edges), 0.05, 1.0))


def _entity(kind: str, fit: fit2d.Fit, points: FloatArray, eid: str) -> Entity:
    if isinstance(fit, fit2d.LineFit):
        return Line(eid, fit.angle, fit.offset)
    ccw = fit2d.arc_sweep(points, fit.center) > 0
    return Arc(eid, fit.center.copy(), fit.radius, ccw)


def fit_chain(raw: FloatArray, closed: bool, tolerance: float, noise: float, ids: list[str]) -> Chain:
    """Lines and arcs (or one circle) through one section polyline."""
    spacing = _spacing(raw, closed)
    samples = fit2d.resample(raw, spacing, closed)
    opts = fit2d.SegmentOptions(tolerance=tolerance)
    if closed:
        circle = fit2d.fit_circle(samples)
        if circle is not None and circle.max_error <= tolerance:
            return Chain([Circle(ids.pop(0), circle.center, circle.radius)], [samples], [], True)
    sigma = max(noise, tolerance / NOISE_FACTOR)
    pts, segments = fit2d.split_polyline(samples, closed, sigma, spacing, opts)
    entities: list[Entity] = []
    point_sets: list[FloatArray] = []
    junctions: list[FloatArray] = []
    for seg in segments:
        points = pts[seg.start : seg.end + 1]
        entities.append(_entity(seg.kind, seg.fit, points, ids.pop(0)))
        point_sets.append(points)
        junctions.append(pts[seg.end].copy())
    return Chain(entities, point_sets, junctions, closed)


def auto_fit_polylines(
    loops: Sequence[FloatArray],
    chains: Sequence[FloatArray],
    noise: float,
    tolerance: float | None,
    units: SnapUnits,
    rejected_snaps: Sequence[str] = (),
) -> FitOutcome:
    tol = tolerance if tolerance is not None else suggested_tolerance(noise)
    ids = [f"e{i}" for i in range(1, 100000)]
    fitted: list[Chain] = []
    for raw in loops:
        fitted.append(fit_chain(raw, True, tol, noise, ids))
    for raw in chains:
        if len(raw) >= 2:
            fitted.append(fit_chain(raw, False, tol, noise, ids))
    constraints = infer_constraints(fitted, ConstraintOptions.for_tolerance(tol))
    solve(fitted, constraints)
    update_junctions(fitted, constraints)
    snaps = find_snaps(fitted, constraints, max(noise, 1e-4), units, rejected_snaps)
    if snaps:
        solve(fitted, constraints, [s.fixed for s in snaps])
        update_junctions(fitted, constraints)
    return FitOutcome(fitted, constraints, snaps, tol, noise)


def fit_single(points: FloatArray, kind: str, tolerance: float, eid: str) -> tuple[Entity, float]:
    """One line or arc through painted points (`auto` picks the better one); its max deviation."""
    opts = fit2d.SegmentOptions(tolerance=tolerance, min_arc_sweep=math.radians(3.0), min_points=3)
    choice: tuple[str, fit2d.Fit] | None
    if kind == "line":
        choice = ("line", fit2d.fit_line(points))
    elif kind == "arc":
        arc = fit2d.fit_kind(points, "arc", opts)
        choice = ("arc", arc) if arc is not None else None
    else:
        line = fit2d.fit_line(points)
        arc = fit2d.fit_kind(points, "arc", opts)
        choice = ("arc", arc) if arc is not None and arc.max_error < 0.5 * line.max_error else ("line", line)
    if choice is None:
        choice = ("line", fit2d.fit_line(points))
    entity = _entity(choice[0], choice[1], points, eid)
    first, last = points[0], points[-1]
    if isinstance(entity, Line):
        n = entity.normal
        entity.start = first - (first @ n - entity.offset) * n
        entity.end = last - (last @ n - entity.offset) * n
    elif isinstance(entity, Arc):
        for name, p in (("start", first), ("end", last)):
            d = p - entity.center
            setattr(entity, name, entity.center + entity.radius * d / np.linalg.norm(d))
    return entity, choice[1].max_error
