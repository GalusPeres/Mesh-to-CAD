"""Automatic sketch fit and constrained refit of an edited sketch.

A fresh fit splits every section polyline into lines and arcs (or one circle),
infers constraints, refits everything jointly, snaps values and refits again
with the snaps fixed. A refit keeps the entities, constraints, snaps and typed
dimensions of an edited sketch and only moves the fitted carriers to the current
section; the shared points follow.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.sketch import fit2d
from m2c_kernel.sketch.carriers import direction_angle, update_points
from m2c_kernel.sketch.constraints import ConstraintOptions, infer_constraints
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    Entity,
    FixedValue,
    FloatArray,
    Line,
    Point,
    WorkSketch,
    entity_distances,
    line_through,
)
from m2c_kernel.sketch.outlines import Outline, add_shape, support_near
from m2c_kernel.sketch.params import SketchDimension, SketchSnap
from m2c_kernel.sketch.section import Section
from m2c_kernel.sketch.shape_entities import BuiltShape
from m2c_kernel.sketch.snaps import find_snaps, fixed_values
from m2c_kernel.sketch.solver import solve
from m2c_kernel.snapping import SnapUnits

MIN_TOLERANCE = 0.05
NOISE_FACTOR = 6.0
"""Tolerance = 6 sigma: the largest of ~2000 Gaussian residuals stays inside (research 1.3)."""
AXIS_TOUCH = 0.5
"""A rotational half-profile ends on the axis if its end lies this close to it (mm)."""


@dataclass(frozen=True)
class FitOutcome:
    sketch: WorkSketch
    constraints: list[Constraint]
    snaps: list[SketchSnap]
    tolerance: float
    noise: float


def suggested_tolerance(noise: float) -> float:
    return max(NOISE_FACTOR * noise, MIN_TOLERANCE)


def section_noise(section: Section) -> float:
    """Robust noise sigma pooled over the raw section polylines (not resampled ones)."""
    estimates = [
        (fit2d.estimate_noise(p, closed=True), len(p)) for p in section.loops if len(p) >= 9
    ] + [(fit2d.estimate_noise(p, closed=False), len(p)) for p in section.chains if len(p) >= 9]
    if not estimates:
        return 0.0
    values = np.array([e for e, _ in estimates])
    weights = np.array([n for _, n in estimates], dtype=np.float64)
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def sample_spacing(raw: FloatArray, closed: bool) -> float:
    """Median raw edge length, clipped to 0.05-1 mm (resampling finer adds no information)."""
    path = np.vstack([raw, raw[:1]]) if closed else raw
    edges = np.linalg.norm(np.diff(path, axis=0), axis=1)
    return float(np.clip(np.median(edges), 0.05, 1.0))


class IdSource:
    """Point ids `p<n>`, entity ids `e<n>` and shape ids `s<n>`, unique within one sketch."""

    def __init__(self, used: Iterable[str] = ()) -> None:
        self._next = {"p": 1, "e": 1, "s": 1}
        for item in used:
            prefix, number = item[:1], item[1:]
            if prefix in self._next and number.isdigit():
                self._next[prefix] = max(self._next[prefix], int(number) + 1)

    @staticmethod
    def of(sketch: WorkSketch) -> IdSource:
        """Ids that are new in this sketch."""
        return IdSource([*sketch.points, *sketch.entities, *(s.id for s in sketch.shapes)])

    def take(self, prefix: str) -> str:
        value = self._next[prefix]
        self._next[prefix] = value + 1
        return f"{prefix}{value}"


def _make_entity(
    kind: str, fit: fit2d.Fit, points: FloatArray, eid: str, start: str, end: str
) -> Entity:
    if isinstance(fit, fit2d.LineFit):
        return Line(eid, fit.angle, fit.offset, start, end)
    ccw = fit2d.arc_sweep(points, fit.center) > 0
    return Arc(eid, fit.center.copy(), fit.radius, ccw, start, end)


def add_polyline(
    sketch: WorkSketch, raw: FloatArray, closed: bool, tolerance: float, ids: IdSource
) -> list[str]:
    """Lines and arcs (or one circle) through one section polyline; returns the point ids."""
    spacing = sample_spacing(raw, closed)
    samples = fit2d.resample(raw, spacing, closed)
    opts = fit2d.SegmentOptions(tolerance=tolerance)
    if closed:
        circle = fit2d.fit_circle(samples)
        if circle is not None and circle.max_error <= tolerance:
            eid = ids.take("e")
            sketch.entities[eid] = Circle(eid, circle.center, circle.radius)
            sketch.samples[eid] = samples
            return []
    # sigma = tolerance / 3 in the BIC cost: the tolerance decides how many entities appear.
    pts, segments = fit2d.split_polyline(samples, closed, tolerance / 3.0, spacing, opts)
    count = len(segments)
    point_ids = [ids.take("p") for _ in range(count if closed else count + 1)]
    if closed:
        for k, seg in enumerate(segments):
            sketch.points[point_ids[k]] = Point(point_ids[k], pts[seg.end].copy())
    else:
        sketch.points[point_ids[0]] = Point(point_ids[0], pts[0].copy())
        for k, seg in enumerate(segments):
            sketch.points[point_ids[k + 1]] = Point(point_ids[k + 1], pts[seg.end].copy())
    for k, seg in enumerate(segments):
        start = point_ids[k - 1] if closed else point_ids[k]
        end = point_ids[k] if closed else point_ids[k + 1]
        points = pts[seg.start : seg.end + 1]
        eid = ids.take("e")
        sketch.entities[eid] = _make_entity(seg.kind, seg.fit, points, eid, start, end)
        sketch.samples[eid] = points
    return point_ids


def assign_points(sketch: WorkSketch, points: FloatArray, band: float) -> dict[str, FloatArray]:
    """Section points per fitted entity: each point goes to the nearest entity within `band`."""
    fitted = [e for e in sketch.entities.values() if e.origin == "fit"]
    if not fitted or len(points) == 0:
        return {}
    distances = np.stack([entity_distances(sketch, e, points) for e in fitted])
    nearest = np.argmin(distances, axis=0)
    keep = distances[nearest, np.arange(len(points))] <= band
    return {e.id: points[(nearest == k) & keep] for k, e in enumerate(fitted)}


def _close_on_axis(sketch: WorkSketch, chains: list[list[str]], ids: IdSource) -> None:
    """Rotational half-profiles that start and end on the axis are closed along it."""
    for point_ids in chains:
        if len(point_ids) < 2:
            continue
        first, last = sketch.points[point_ids[0]], sketch.points[point_ids[-1]]
        if abs(first.xy[1]) > AXIS_TOUCH or abs(last.xy[1]) > AXIS_TOUCH:
            continue
        eid = ids.take("e")
        sketch.entities[eid] = Line(eid, math.pi / 2, 0.0, last.id, first.id, origin="axis")


def _resampled(section: Section) -> FloatArray:
    parts = [fit2d.resample(p, sample_spacing(p, True), True) for p in section.loops if len(p) >= 3]
    parts += [
        fit2d.resample(p, sample_spacing(p, False), False) for p in section.chains if len(p) >= 2
    ]
    return np.vstack(parts) if parts else np.zeros((0, 2))


def fit_points(section: Section) -> FloatArray:
    """The points entities are fitted to: the cut and the support points of the section."""
    cut = _resampled(section)
    return cut if section.support is None else np.vstack([cut, section.support])


def fit_section(
    section: Section,
    tolerance: float | None,
    units: SnapUnits,
    rejected_snaps: Sequence[str] = (),
    snap: bool = True,
    check_cancelled: Callable[[], None] | None = None,
) -> FitOutcome:
    """Fit a new sketch to a section; `snap=False` leaves the measured values.

    Closed outlines of a planar section that are a simple shape (circle, slot,
    rounded rectangle, ring arm) become that shape; the rest is split into lines
    and arcs.
    """
    noise = section_noise(section)
    tol = tolerance if tolerance is not None else suggested_tolerance(noise)
    sketch = WorkSketch()
    ids = IdSource()
    built: list[BuiltShape] = []
    for raw in section.loops:
        shape = (
            None if section.rotational else _add_shape(sketch, section, raw, tol, units, ids, snap)
        )
        if shape is not None:
            built.append(shape)
        else:
            add_polyline(sketch, raw, True, tol, ids)
        if check_cancelled is not None:
            check_cancelled()
    open_chains = [
        add_polyline(sketch, raw, False, tol, ids) for raw in section.chains if len(raw) >= 2
    ]
    if section.rotational:
        _close_on_axis(sketch, open_chains, ids)
    shaped = {e for shape in built for e in shape.shape.entities}
    constraints = infer_constraints(sketch, ConstraintOptions.for_tolerance(tol), exclude=shaped)
    constraints += [c for shape in built for c in shape.constraints]
    shape_snaps = [s for shape in built for s in shape.snaps if s.id not in rejected_snaps]
    held = [f for s in shape_snaps for f in fixed_values(sketch, s)]
    solve(sketch, constraints, held, check_cancelled=check_cancelled)
    update_points(sketch, constraints)
    # The split leaves the samples around each breakpoint with whichever entity the
    # dynamic programme chose; near a tangent transition that biases radii. Handing
    # every point to its nearest fitted entity and solving again removes the bias.
    reassigned = assign_points(sketch, fit_points(section), max(3.0 * tol, 0.3))
    sketch.samples.update({eid: pts for eid, pts in reassigned.items() if len(pts) >= 5})
    solve(sketch, constraints, held, check_cancelled=check_cancelled)
    update_points(sketch, constraints)
    if not snap:
        return FitOutcome(sketch, constraints, [], tol, noise)
    snaps = shape_snaps + find_snaps(sketch, constraints, max(noise, 1e-4), units, rejected_snaps)
    if snaps:
        fixed = [f for s in snaps for f in fixed_values(sketch, s)]
        solve(sketch, constraints, fixed, check_cancelled=check_cancelled)
        update_points(sketch, constraints)
    return FitOutcome(sketch, constraints, snaps, tol, noise)


def _add_shape(
    sketch: WorkSketch,
    section: Section,
    raw: FloatArray,
    tolerance: float,
    units: SnapUnits,
    ids: IdSource,
    designed: bool,
) -> BuiltShape | None:
    samples = fit2d.resample(raw, sample_spacing(raw, True), True)
    band = max(3.0 * tolerance, 0.3)
    outline = Outline(raw, samples)
    support = support_near(section, samples, band)
    return add_shape(sketch, outline, support, tolerance, units, ids.take, designed=designed)


def dimension_values(sketch: WorkSketch, dimensions: Sequence[SketchDimension]) -> list[FixedValue]:
    values: list[FixedValue] = []
    for dim in dimensions:
        entity = sketch.entities.get(dim.entity)
        if entity is None:
            continue
        match dim.kind:
            case "length":
                values.append(FixedValue(dim.entity, "length", dim.value))
            case "angle" if isinstance(entity, Line):
                target = math.radians(dim.value) - math.pi / 2
                if math.cos(target - entity.angle) < 0:
                    target += math.pi
                values.append(FixedValue(dim.entity, "angle", target))
            case "radius":
                values.append(FixedValue(dim.entity, "radius", dim.value))
            case "centerX":
                values.append(FixedValue(dim.entity, "x", dim.value))
            case "centerY":
                values.append(FixedValue(dim.entity, "y", dim.value))
    return values


def refit(
    sketch: WorkSketch,
    constraints: list[Constraint],
    snaps: Sequence[SketchSnap],
    dimensions: Sequence[SketchDimension],
    section: Section,
    tolerance: float,
) -> None:
    """Move the fitted carriers of an edited sketch to the section, keeping all fixed values."""
    assigned = assign_points(sketch, fit_points(section), max(3.0 * tolerance, 0.3))
    sketch.samples = {eid: pts for eid, pts in assigned.items() if len(pts) >= 3}
    fixed = [f for s in snaps for f in fixed_values(sketch, s)]
    fixed += dimension_values(sketch, dimensions)
    solve(sketch, constraints, fixed)
    update_points(sketch, constraints)


PAINT_AXIS_DEG = 0.5
"""A painted line this close to an axis direction becomes horizontal or vertical."""


def axis_of_painted(entity: Entity) -> Literal["horizontal", "vertical"] | None:
    if not isinstance(entity, Line):
        return None
    direction = math.degrees(direction_angle(entity))
    if min(direction, 180.0 - direction) <= PAINT_AXIS_DEG:
        return "horizontal"
    if abs(direction - 90.0) <= PAINT_AXIS_DEG:
        return "vertical"
    return None


def fit_single(
    points: FloatArray, kind: str, tolerance: float
) -> tuple[Line | Arc, FloatArray, FloatArray, float]:
    """One line or arc through painted points (`auto` picks the better one).

    Returns the entity (without point ids), its start and end on the carrier and the
    largest distance of the points from it.
    """
    opts = fit2d.SegmentOptions(tolerance=tolerance, min_arc_sweep=math.radians(3.0), min_points=3)
    line = fit2d.fit_line(points)
    arc = fit2d.fit_circle(points) if kind != "line" and len(points) >= 3 else None
    if arc is not None and arc.radius > opts.max_radius:
        arc = None
    first, last = points[0], points[-1]
    if arc is not None and (kind == "arc" or arc.max_error < 0.5 * line.max_error):
        ccw = fit2d.arc_sweep(points, arc.center) > 0
        entity: Line | Arc = Arc("", arc.center, arc.radius, ccw, "", "")
        ends = [
            arc.center + arc.radius * (p - arc.center) / np.linalg.norm(p - arc.center)
            for p in (first, last)
        ]
        return entity, ends[0], ends[1], arc.max_error
    fitted = Line("", line.angle, line.offset, "", "")
    n = fitted.normal
    start = first - (first @ n - fitted.offset) * n
    end = last - (last @ n - fitted.offset) * n
    fitted.angle, fitted.offset = line_through(start, end)
    return fitted, start, end, line.max_error
