"""Conversion between the stored sketch (`SketchParams`) and the working model."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from m2c_kernel.sketch.model import Arc, Circle, Constraint, Line, Point, WorkSketch, line_through
from m2c_kernel.sketch.params import (
    ArcEntity,
    CircleEntity,
    LineEntity,
    SketchConstraint,
    SketchEntity,
    SketchParams,
    SketchPoint,
    SketchSnap,
)

DECIMALS = 9
"""Stored coordinates are rounded to a nanometre, which keeps the stored JSON tidy."""


class InvalidSketchError(ValueError):
    """Stored geometry that references missing points or has duplicate ids."""


def _round(value: float) -> float:
    return round(float(value), DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0


def to_work(params: SketchParams) -> tuple[WorkSketch, list[Constraint]]:
    sketch = WorkSketch()
    for point in params.points:
        if point.id in sketch.points:
            raise InvalidSketchError(f"duplicate point {point.id}")
        sketch.points[point.id] = Point(
            point.id, np.array([point.x, point.y], dtype=np.float64), point.fixed
        )
    for entity in params.entities:
        if entity.id in sketch.entities:
            raise InvalidSketchError(f"duplicate entity {entity.id}")
        if isinstance(entity, CircleEntity):
            sketch.entities[entity.id] = Circle(
                entity.id, np.asarray(entity.center, dtype=np.float64), entity.radius, entity.origin
            )
            continue
        for pid in (entity.start, entity.end):
            if pid not in sketch.points:
                raise InvalidSketchError(f"{entity.id} references missing point {pid}")
        if isinstance(entity, LineEntity):
            start, end = sketch.xy(entity.start), sketch.xy(entity.end)
            if entity.origin == "axis":
                angle, offset = math.pi / 2, 0.0
            else:
                angle, offset = line_through(start, end)
            sketch.entities[entity.id] = Line(
                entity.id, angle, offset, entity.start, entity.end, entity.origin
            )
        else:
            sketch.entities[entity.id] = Arc(
                entity.id,
                np.asarray(entity.center, dtype=np.float64),
                entity.radius,
                entity.ccw,
                entity.start,
                entity.end,
                entity.origin,
            )
    constraints = [
        Constraint(c.kind, tuple(c.refs))
        for c in params.constraints
        if all(ref in sketch.entities for ref in c.refs)
    ]
    return sketch, constraints


def to_params(
    base: SketchParams,
    sketch: WorkSketch,
    constraints: list[Constraint],
    snaps: list[SketchSnap] | None = None,
) -> SketchParams:
    """`base` with the geometry of the working sketch (entity order preserved)."""
    used = {
        pid
        for e in sketch.entities.values()
        if not isinstance(e, Circle)
        for pid in (e.start, e.end)
    }
    points = [
        SketchPoint(id=p.id, x=_round(p.xy[0]), y=_round(p.xy[1]), fixed=p.fixed)
        for p in sketch.points.values()
        if p.id in used
    ]
    entities: list[SketchEntity] = []
    for e in sketch.entities.values():
        if isinstance(e, Line):
            entities.append(LineEntity(id=e.id, start=e.start, end=e.end, origin=e.origin))
        elif isinstance(e, Arc):
            entities.append(
                ArcEntity(
                    id=e.id,
                    start=e.start,
                    end=e.end,
                    center=(_round(e.center[0]), _round(e.center[1])),
                    radius=_round(e.radius),
                    ccw=e.ccw,
                    origin=e.origin,
                )
            )
        else:
            entities.append(
                CircleEntity(
                    id=e.id,
                    center=(_round(e.center[0]), _round(e.center[1])),
                    radius=_round(e.radius),
                    origin=e.origin,
                )
            )
    return replace(
        base,
        points=points,
        entities=entities,
        constraints=[SketchConstraint(kind=c.kind, refs=list(c.refs)) for c in constraints],
        snaps=base.snaps if snaps is None else snaps,
    )
