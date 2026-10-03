"""A fillet at a sketch corner with the radius measured on the scan (Ctrl at a joint).

The section points that round the corner are the ones near the joint that lie off
both neighbouring entities. An arc tangent to both neighbours is fitted to them by
the joint solver (the neighbours stay where they are), and its radius snaps to a
design value when the refit with that radius stays as close to the points
(`shape_intent.KEEP_FACTOR`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from m2c_kernel.codes.sketch import ErrorCode
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.sketch.autofit import IdSource
from m2c_kernel.sketch.carriers import away_direction, update_points
from m2c_kernel.sketch.convert import to_params, to_work
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    FixedValue,
    FloatArray,
    Point,
    WorkSketch,
    carrier_distances,
)
from m2c_kernel.sketch.params import SketchParams, SketchSnap
from m2c_kernel.sketch.shape_intent import KEEP_ALLOWANCE, KEEP_FACTOR
from m2c_kernel.sketch.snaps import fixed_values
from m2c_kernel.sketch.solver import solve
from m2c_kernel.snapping import SnapUnits, steps_for

MIN_POINTS = 5
REACH_SHARE = 0.45
"""Rounding points are searched within this share of the shorter neighbour's length."""
MIN_TURN = math.radians(10.0)
"""Joints that turn less than this are smooth: there is no corner to round."""


@dataclass(frozen=True)
class FilletResult:
    params: SketchParams
    entity: str
    radius: float
    measured: float


def _corner(sketch: WorkSketch, point_id: str) -> tuple[str, str]:
    ends = [e for e, _ in sketch.incidence().get(point_id, [])]
    if len(ends) != 2 or any(isinstance(e, Circle) for e in ends):
        raise KernelError(ErrorCode.NO_CORNER)
    return ends[0].id, ends[1].id


def _length(sketch: WorkSketch, entity_id: str) -> float:
    entity = sketch.entities[entity_id]
    assert not isinstance(entity, Circle)
    chord = float(np.linalg.norm(sketch.xy(entity.end) - sketch.xy(entity.start)))
    return chord if not isinstance(entity, Arc) else max(chord, 1e-6)


def rounding_points(
    sketch: WorkSketch, point_id: str, points: FloatArray, tolerance: float
) -> FloatArray:
    """Section points near the joint that lie off both carriers."""
    a, b = _corner(sketch, point_id)
    reach = REACH_SHARE * min(_length(sketch, a), _length(sketch, b))
    near = points[np.linalg.norm(points - sketch.xy(point_id), axis=1) <= reach]
    off = (carrier_distances(sketch.entities[a], near) > 1.5 * tolerance) & (
        carrier_distances(sketch.entities[b], near) > 1.5 * tolerance
    )
    result: FloatArray = near[off]
    return result


def _start_arc(sketch: WorkSketch, point_id: str, a: str, b: str, radius: float) -> Arc:
    """A first guess of the fillet from the tangents at the joint."""
    da = away_direction(sketch, sketch.entities[a], point_id)
    db = away_direction(sketch, sketch.entities[b], point_id)
    turn = math.acos(float(np.clip(-(da @ db), -1.0, 1.0)))
    if turn < MIN_TURN:
        raise KernelError(ErrorCode.NO_CORNER)
    bisector = (da + db) / max(float(np.linalg.norm(da + db)), 1e-12)
    half = (math.pi - turn) / 2.0
    center = sketch.xy(point_id) + radius / math.sin(half) * bisector
    ccw = float(db[1] * da[0] - db[0] * da[1]) < 0  # a left turn from -da to db
    return Arc("", center, radius, ccw, "", "")


def _rms(sketch: WorkSketch, arc_id: str, points: FloatArray) -> float:
    return float(np.sqrt(np.mean(carrier_distances(sketch.entities[arc_id], points) ** 2)))


def fillet_corner(
    params: SketchParams,
    section_points: FloatArray,
    point_id: str,
    tolerance: float,
    units: SnapUnits,
) -> FilletResult:
    """Round the corner at `point_id` with the radius the scan shows there."""
    sketch, constraints = to_work(params)
    if point_id not in sketch.points:
        raise KernelError(ErrorCode.NO_CORNER)
    a, b = _corner(sketch, point_id)
    rounding = rounding_points(sketch, point_id, section_points, tolerance)
    if len(rounding) < MIN_POINTS:
        raise KernelError(ErrorCode.NO_CORNER)
    guess = max(float(np.median(np.linalg.norm(rounding - sketch.xy(point_id), axis=1))), 0.05)
    arc = _start_arc(sketch, point_id, a, b, guess)
    ids = IdSource.of(sketch)
    arc_id, start_id, end_id = ids.take("e"), ids.take("p"), ids.take("p")
    joint = sketch.xy(point_id).copy()
    sketch.points[start_id] = Point(start_id, joint.copy())
    sketch.points[end_id] = Point(end_id, joint.copy())
    for eid, new_point in ((a, start_id), (b, end_id)):
        entity = sketch.entities[eid]
        assert not isinstance(entity, Circle)
        if entity.start == point_id:
            entity.start = new_point
        else:
            entity.end = new_point
    del sketch.points[point_id]
    sketch.entities[arc_id] = Arc(arc_id, arc.center, arc.radius, arc.ccw, start_id, end_id)
    sketch.samples[arc_id] = rounding
    constraints += [Constraint("tangent", (a, arc_id)), Constraint("tangent", (arc_id, b))]
    held = [f for s in params.snaps for f in fixed_values(sketch, s)]
    solve(sketch, constraints, held, only=[arc_id])
    fitted = sketch.entities[arc_id]
    assert isinstance(fitted, Arc)
    measured, free_rms = fitted.radius, _rms(sketch, arc_id, rounding)
    limit = free_rms * KEEP_FACTOR + KEEP_ALLOWANCE * tolerance
    snaps = list(params.snaps)
    for step in steps_for(units):
        value = round(measured / step) * step
        if value <= 0 or abs(value - measured) > max(tolerance, 0.1 * measured):
            continue
        solve(sketch, constraints, [*held, FixedValue(arc_id, "radius", value)], only=[arc_id])
        if _rms(sketch, arc_id, rounding) <= limit:
            snaps.append(
                SketchSnap(
                    id=f"{arc_id}:radius",
                    entity=arc_id,
                    kind="radius",
                    value=value,
                    measured=measured,
                    uncertainty=0.0,
                )
            )
            break
    else:
        solve(sketch, constraints, held, only=[arc_id])
    update_points(sketch, constraints)
    radius = sketch.entities[arc_id]
    assert isinstance(radius, Arc)
    return FilletResult(
        to_params(params, sketch, constraints, snaps), arc_id, radius.radius, measured
    )
