"""Sketch gestures on the section: a click inside an outline fits its shape.

Each gesture edits one part of an existing sketch and leaves the rest where it is:
only the new entities are solved, the other entities keep their carriers. The
result carries the whole sketch, so the panel takes it as one undo step.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace

from m2c_kernel.codes.sketch import ErrorCode
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.sketch import fit2d
from m2c_kernel.sketch.autofit import IdSource, add_polyline
from m2c_kernel.sketch.carriers import update_points
from m2c_kernel.sketch.constraints import ConstraintOptions, infer_constraints
from m2c_kernel.sketch.convert import to_params, to_work
from m2c_kernel.sketch.model import Circle, Constraint, FloatArray, WorkSketch
from m2c_kernel.sketch.noise import sample_spacing
from m2c_kernel.sketch.outlines import (
    CLICK_LENIENCY,
    Outline,
    add_shape,
    entities_on,
    outline_at,
    support_near,
)
from m2c_kernel.sketch.params import ShapeKind, SketchParams, SketchSnap
from m2c_kernel.sketch.section import Section
from m2c_kernel.sketch.snaps import find_snaps, fixed_values
from m2c_kernel.sketch.solver import solve
from m2c_kernel.snapping import SnapUnits


@dataclass(frozen=True)
class GestureResult:
    params: SketchParams
    entities: list[str]
    """The entities the gesture added."""
    kind: ShapeKind | None
    """The recognised shape, None for a free profile."""


def remove_entities(
    params: SketchParams,
    sketch: WorkSketch,
    constraints: list[Constraint],
    removed: Collection[str],
) -> tuple[SketchParams, list[Constraint]]:
    """Take entities out of the working sketch and everything that refers to them."""
    gone = set(removed)
    for eid in gone:
        sketch.entities.pop(eid, None)
        sketch.samples.pop(eid, None)
    used = {
        pid
        for e in sketch.entities.values()
        if not isinstance(e, Circle)
        for pid in (e.start, e.end)
    }
    sketch.points = {pid: p for pid, p in sketch.points.items() if pid in used}
    sketch.shapes = [s for s in sketch.shapes if not gone.intersection(s.entities)]
    kept = [c for c in constraints if not gone.intersection(c.refs)]
    cleaned = replace(
        params,
        snaps=[
            s for s in params.snaps if s.entity not in gone and not gone.intersection(s.members)
        ],
        dimensions=[d for d in params.dimensions if d.entity not in gone],
    )
    return cleaned, kept


def fit_outline(
    params: SketchParams,
    section: Section,
    point: FloatArray,
    units: SnapUnits,
    tolerance: float,
    noise: float,
) -> GestureResult:
    """Fit the shape of the closed outline around `point`, replacing what was fitted to it.

    The shape (circle, slot, rounded rectangle, ring arm) gets design values; an
    outline that is no such shape is split into lines and arcs with their constraints
    and snaps.
    """
    raw = outline_at(section, point)
    if raw is None:
        raise KernelError(ErrorCode.NO_OUTLINE)
    sketch, constraints = to_work(params)
    samples = fit2d.resample(raw, sample_spacing(raw, True), True)
    band = max(3.0 * tolerance, 0.3)
    params, constraints = remove_entities(
        params, sketch, constraints, entities_on(sketch, samples, band)
    )
    ids = IdSource.of(sketch)
    before = set(sketch.entities)
    support = support_near(section, samples, band)
    built = add_shape(
        sketch, Outline(raw, samples), support, tolerance, units, ids.take, CLICK_LENIENCY
    )
    opts = ConstraintOptions.for_tolerance(tolerance)
    new_snaps: list[SketchSnap] = []
    if built is None:
        add_polyline(sketch, raw, True, tolerance, ids)
        new = [e for e in sketch.entities if e not in before]
        constraints += infer_constraints(sketch, opts, only=new)
    else:
        new = list(built.shape.entities)
        constraints += built.constraints + infer_constraints(sketch, opts, only=new, exclude=new)
        new_snaps = [s for s in built.snaps if s.id not in params.rejected_snaps]
    snaps = [*params.snaps, *new_snaps]
    solve(sketch, constraints, [f for s in snaps for f in fixed_values(sketch, s)], only=new)
    update_points(sketch, constraints)
    if built is None:
        found = find_snaps(sketch, constraints, max(noise, 1e-4), units, params.rejected_snaps, new)
        snaps += found
        if found:
            solve(
                sketch, constraints, [f for s in snaps for f in fixed_values(sketch, s)], only=new
            )
            update_points(sketch, constraints)
    result = to_params(params, sketch, constraints, snaps)
    return GestureResult(result, new, built.shape.kind if built else None)
