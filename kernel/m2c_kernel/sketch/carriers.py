"""Carriers of sketch entities: directions, intersections and the shared points.

Lines are kept in normal form and arcs as circles; the end points of fitted
entities are never stored as data but computed from the carriers that meet there,
so consecutive entities join without gaps (research 1.7).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from m2c_kernel.sketch.model import (
    Circle,
    Constraint,
    Entity,
    FloatArray,
    Line,
    WorkSketch,
    line_through,
)


def direction_angle(line: Line) -> float:
    """Direction of a line modulo 180 degrees, in [0, pi)."""
    return (line.angle + math.pi / 2) % math.pi


def angle_gap(a: float, b: float) -> float:
    d = (a - b) % math.pi
    return min(d, math.pi - d)


def is_carrier(entity: Entity) -> bool:
    """Whether the entity's own curve defines its end points (drawn lines follow their points)."""
    return not (isinstance(entity, Line) and entity.origin == "drawn")


def away_direction(sketch: WorkSketch, entity: Entity, point_id: str) -> FloatArray:
    """Unit tangent at one end of an entity, pointing into the entity."""
    assert not isinstance(entity, Circle)
    at_start = entity.start == point_id
    p = sketch.xy(point_id)
    if isinstance(entity, Line):
        d = sketch.xy(entity.end) - sketch.xy(entity.start)
        length = float(np.linalg.norm(d))
        d = d / length if length > 1e-12 else entity.direction
    else:
        radial = p - entity.center
        radial = radial / max(float(np.linalg.norm(radial)), 1e-12)
        d = np.array([-radial[1], radial[0]]) * (1.0 if entity.ccw else -1.0)
    return d if at_start else -d


def tangent_gap(a: Entity, b: Entity) -> float:
    if isinstance(a, Line) or isinstance(b, Line):
        line, round_ = (a, b) if isinstance(a, Line) else (b, a)
        assert isinstance(line, Line) and not isinstance(round_, Line)
        return abs(abs(float(round_.center @ line.normal) - line.offset) - round_.radius)
    d = float(np.linalg.norm(a.center - b.center))
    return min(abs(d - (a.radius + b.radius)), abs(d - abs(a.radius - b.radius)))


def line_line(a: Line, b: Line, hint: FloatArray) -> FloatArray:
    m = np.array([a.normal, b.normal])
    if abs(np.linalg.det(m)) < 1e-3:
        projected: FloatArray = hint - (hint @ m[0] - a.offset) * m[0]
        return projected
    result: FloatArray = np.linalg.solve(m, [a.offset, b.offset])
    return result


def line_circle(
    line: Line, center: FloatArray, radius: float, hint: FloatArray, tangent: bool
) -> FloatArray:
    n = line.normal
    foot = center - (center @ n - line.offset) * n
    if tangent:
        return foot
    half = math.sqrt(max(radius**2 - float(np.sum((foot - center) ** 2)), 0.0))
    t = np.array([-n[1], n[0]])
    options = [foot + half * t, foot - half * t]
    return min(options, key=lambda p: float(np.linalg.norm(p - hint)))


def circle_circle(
    c1: FloatArray, r1: float, c2: FloatArray, r2: float, hint: FloatArray, tangent: bool
) -> FloatArray:
    d = float(np.linalg.norm(c2 - c1))
    if d < 1e-6:
        return c1 + r1 * (hint - c1) / max(float(np.linalg.norm(hint - c1)), 1e-12)
    u = (c2 - c1) / d
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    base = c1 + a * u
    if tangent:
        # The touching point lies on the first circle, on the line of centres.
        return c1 + r1 * u * (1.0 if a >= 0 else -1.0)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    perp = np.array([-u[1], u[0]])
    options = [base + h * perp, base - h * perp]
    return min(options, key=lambda p: float(np.linalg.norm(p - hint)))


def intersect(a: Entity, b: Entity, hint: FloatArray, tangent: bool = False) -> FloatArray:
    """The common point of two carriers closest to the hint (the touching point if tangent)."""
    if isinstance(a, Line) and isinstance(b, Line):
        return line_line(a, b, hint)
    if isinstance(a, Line):
        assert not isinstance(b, Line)
        return line_circle(a, b.center, b.radius, hint, tangent)
    if isinstance(b, Line):
        return line_circle(b, a.center, a.radius, hint, tangent)
    return circle_circle(a.center, a.radius, b.center, b.radius, hint, tangent)


def project(entity: Entity, point: FloatArray) -> FloatArray:
    if isinstance(entity, Line):
        result: FloatArray = point - (point @ entity.normal - entity.offset) * entity.normal
        return result
    direction = point - entity.center
    return entity.center + entity.radius * direction / max(float(np.linalg.norm(direction)), 1e-12)


def point_position(
    sketch: WorkSketch,
    point_id: str,
    carriers: Mapping[str, Entity],
    incidence: Mapping[str, list[tuple[Entity, str]]],
    tangent_pairs: set[frozenset[str]],
    pinned: set[str],
) -> FloatArray:
    """Where a shared point lies, given the carriers of the entities that meet there.

    Two carriers: their intersection nearest the previous position (the touching
    point if they are tangent). One carrier: the previous position projected onto
    it. Pinned points and points of drawn lines only stay where they are.
    """
    hint = sketch.xy(point_id)
    if point_id in pinned:
        return hint
    around = [carriers[e.id] for e, _ in incidence[point_id] if is_carrier(e)]
    if len(around) >= 2:
        a, b = around[0], around[1]
        return intersect(a, b, hint, frozenset((a.id, b.id)) in tangent_pairs)
    if len(around) == 1:
        return project(around[0], hint)
    return hint


def update_points(sketch: WorkSketch, constraints: Sequence[Constraint]) -> None:
    """Recompute every shared point from the carriers, so entities meet without gaps."""
    tangent_pairs = {frozenset(c.refs) for c in constraints if c.kind == "tangent"}
    pinned = {pid for pid, p in sketch.points.items() if p.fixed}
    incidence = sketch.incidence()
    positions = {
        pid: point_position(sketch, pid, sketch.entities, incidence, tangent_pairs, pinned)
        for pid in sketch.points
    }
    for pid, xy in positions.items():
        sketch.points[pid].xy = np.asarray(xy, dtype=np.float64)
    for entity in sketch.entities.values():
        if isinstance(entity, Line) and entity.origin == "drawn":
            entity.angle, entity.offset = line_through(
                sketch.xy(entity.start), sketch.xy(entity.end)
            )
