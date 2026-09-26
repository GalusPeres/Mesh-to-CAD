"""Constraint inference, joint penalty least-squares refit and exact junctions.

Methods: `.work/research/algorithms-cad.md` 1.6-1.8. Constraints and snapped
values are residuals with a large weight; junctions are computed from the
refitted entities, so consecutive entities share identical endpoints.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.sketch.model import (
    Arc,
    Chain,
    Circle,
    Constraint,
    Entity,
    FixedValue,
    FloatArray,
    Line,
)

WEIGHT = 1e4


@dataclass(frozen=True)
class ConstraintOptions:
    angle_tol: float = math.radians(1.0)
    tangent_gap: float = 0.25
    """|dist(centre, line) - r| or the circle-circle gap in mm."""
    tangent_angle_tol: float = math.radians(20.0)
    radius_tol: float = 0.15
    center_tol: float = 0.15

    @staticmethod
    def for_tolerance(tol: float) -> ConstraintOptions:
        return ConstraintOptions(tangent_gap=2.0 * tol, radius_tol=1.5 * tol, center_tol=1.5 * tol)


def _direction_angle(line: Line) -> float:
    return (line.angle + math.pi / 2) % math.pi


def _angle_gap(a: float, b: float) -> float:
    d = (a - b) % math.pi
    return min(d, math.pi - d)


def _tangent_at(entity: Entity, point: FloatArray, points: FloatArray) -> FloatArray:
    """Unit tangent in traversal direction at a point of the entity."""
    if isinstance(entity, Line):
        t = np.array([-math.sin(entity.angle), math.cos(entity.angle)])
        return t if t @ (points[-1] - points[0]) >= 0 else -t
    radial = (point - entity.center) / max(float(np.linalg.norm(point - entity.center)), 1e-12)
    t = np.array([-radial[1], radial[0]])
    return t if isinstance(entity, Arc) and entity.ccw else -t


def _tangent_gap(a: Entity, b: Entity) -> float:
    if isinstance(a, Line) or isinstance(b, Line):
        line, circle = (a, b) if isinstance(a, Line) else (b, a)
        assert isinstance(line, Line) and not isinstance(circle, Line)
        return abs(abs(float(circle.center @ line.normal) - line.offset) - circle.radius)
    d = float(np.linalg.norm(a.center - b.center))
    return min(abs(d - (a.radius + b.radius)), abs(d - abs(a.radius - b.radius)))


def infer_constraints(chains: Sequence[Chain], opts: ConstraintOptions) -> list[Constraint]:
    """Infer constraints between entities.

    Horizontal/vertical, parallel, perpendicular, collinear, equal radius, concentric, tangent.
    """
    constraints: list[Constraint] = []
    lines = [e for c in chains for e in c.entities if isinstance(e, Line)]
    rounds = [e for c in chains for e in c.entities if not isinstance(e, Line)]

    groups: list[list[Line]] = []
    for line in sorted(lines, key=_direction_angle):
        if (
            groups
            and _angle_gap(_direction_angle(groups[-1][0]), _direction_angle(line)) < opts.angle_tol
        ):
            groups[-1].append(line)
        else:
            groups.append([line])
    if (
        len(groups) > 1
        and _angle_gap(_direction_angle(groups[0][0]), _direction_angle(groups[-1][0]))
        < opts.angle_tol
    ):
        groups[0] = groups.pop() + groups[0]

    free_groups: list[list[Line]] = []
    for group in groups:
        mean = _direction_angle(group[0])
        axis = (
            "horizontal"
            if min(mean, math.pi - mean) < opts.angle_tol
            else "vertical"
            if abs(mean - math.pi / 2) < opts.angle_tol
            else None
        )
        if axis == "horizontal":
            constraints.extend(Constraint("horizontal", (line.id,)) for line in group)
        elif axis == "vertical":
            constraints.extend(Constraint("vertical", (line.id,)) for line in group)
        else:
            free_groups.append(group)
        carriers: list[Line] = []
        for line in group:
            host = next(
                (
                    c
                    for c in carriers
                    if abs(line.offset * math.cos(c.angle - line.angle) - c.offset)
                    < opts.center_tol
                ),
                None,
            )
            if host is not None:
                constraints.append(Constraint("collinear", (host.id, line.id)))
            else:
                if carriers and axis is None:
                    constraints.append(Constraint("parallel", (carriers[0].id, line.id)))
                carriers.append(line)

    for i, gi in enumerate(free_groups):
        for gj in free_groups[i + 1 :]:
            gap = _angle_gap(_direction_angle(gi[0]), _direction_angle(gj[0]))
            if abs(gap - math.pi / 2) < opts.angle_tol:
                constraints.append(Constraint("perpendicular", (gi[0].id, gj[0].id)))

    order = sorted(rounds, key=lambda e: e.radius)
    for a, b in itertools.pairwise(order):
        if abs(a.radius - b.radius) < opts.radius_tol:
            constraints.append(Constraint("equalRadius", (a.id, b.id)))
    for i, a in enumerate(rounds):
        for b in rounds[i + 1 :]:
            if np.linalg.norm(a.center - b.center) < opts.center_tol:
                constraints.append(Constraint("concentric", (a.id, b.id)))

    for chain in chains:
        n = len(chain.entities)
        pairs = range(n if chain.closed else n - 1) if n > 1 else range(0)
        for k in pairs:
            a, b = chain.entities[k], chain.entities[(k + 1) % n]
            if isinstance(a, Line) and isinstance(b, Line):
                continue
            joint = chain.junctions[k]
            ta = _tangent_at(a, joint, chain.points[k])
            tb = _tangent_at(b, joint, chain.points[(k + 1) % n])
            if math.acos(float(np.clip(ta @ tb, -1, 1))) > opts.tangent_angle_tol:
                continue
            if _tangent_gap(a, b) <= opts.tangent_gap:
                constraints.append(Constraint("tangent", (a.id, b.id)))
    return constraints


def solve(
    chains: Sequence[Chain],
    constraints: Sequence[Constraint],
    fixed: Sequence[FixedValue] = (),
    max_points_per_entity: int = 200,
) -> None:
    """Refit all entities jointly; constraints and fixed values are weighted residuals."""
    entities: dict[str, Entity] = {e.id: e for c in chains for e in c.entities}
    points = {e.id: p for c in chains for e, p in zip(c.entities, c.points, strict=True)}
    layout: dict[str, int] = {}
    x0: list[float] = []
    for eid, e in entities.items():
        layout[eid] = len(x0)
        x0 += [e.angle, e.offset] if isinstance(e, Line) else [*e.center, e.radius]
    tangent_sign: dict[tuple[str, ...], float] = {}
    for c in constraints:
        if c.kind == "tangent" and all(not isinstance(entities[r], Line) for r in c.refs):
            a, b = (entities[r] for r in c.refs)
            assert not isinstance(a, Line) and not isinstance(b, Line)
            dist = float(np.linalg.norm(a.center - b.center))
            external = abs(dist - (a.radius + b.radius)) < abs(dist - abs(a.radius - b.radius))
            tangent_sign[c.refs] = 1.0 if external else -1.0
    samples = {
        eid: p[np.linspace(0, len(p) - 1, min(len(p), max_points_per_entity)).astype(int)]
        for eid, p in points.items()
    }
    active = [c for c in constraints if all(r in entities for r in c.refs)]
    fixed = [f for f in fixed if f.entity in entities]

    def unpack(x: FloatArray, eid: str) -> FloatArray:
        i = layout[eid]
        return x[i : i + 2] if isinstance(entities[eid], Line) else x[i : i + 3]

    def residuals(x: FloatArray) -> FloatArray:
        out: list[FloatArray | list[float]] = []
        for eid, p in samples.items():
            v = unpack(x, eid)
            if isinstance(entities[eid], Line):
                out.append(p @ np.array([math.cos(v[0]), math.sin(v[0])]) - v[1])
            else:
                out.append(np.linalg.norm(p - v[:2], axis=1) - v[2])
        for c in active:
            v = [unpack(x, r) for r in c.refs]
            match c.kind:
                case "horizontal":
                    out.append([WEIGHT * math.cos(v[0][0])])
                case "vertical":
                    out.append([WEIGHT * math.sin(v[0][0])])
                case "parallel":
                    out.append([WEIGHT * math.sin(v[0][0] - v[1][0])])
                case "perpendicular":
                    out.append([WEIGHT * math.cos(v[0][0] - v[1][0])])
                case "collinear":
                    out.append(
                        [
                            WEIGHT * math.sin(v[0][0] - v[1][0]),
                            WEIGHT * (v[1][1] * math.cos(v[0][0] - v[1][0]) - v[0][1]),
                        ]
                    )
                case "equalRadius":
                    out.append([WEIGHT * (v[0][2] - v[1][2])])
                case "concentric":
                    out.append(WEIGHT * (v[0][:2] - v[1][:2]))
                case "tangent":
                    first_is_line = isinstance(entities[c.refs[0]], Line)
                    if first_is_line or isinstance(entities[c.refs[1]], Line):
                        line, circ = (v[0], v[1]) if first_is_line else (v[1], v[0])
                        normal = np.array([math.cos(line[0]), math.sin(line[0])])
                        dist = abs(float(circ[:2] @ normal) - line[1])
                        out.append([WEIGHT * (dist - circ[2])])
                    else:
                        s = tangent_sign[c.refs]
                        gap = np.linalg.norm(v[0][:2] - v[1][:2]) - abs(v[0][2] + s * v[1][2])
                        out.append([WEIGHT * gap])
        for f in fixed:
            v = unpack(x, f.entity)
            match f.kind:
                case "radius":
                    out.append([WEIGHT * (v[2] - f.value)])
                case "x":
                    out.append([WEIGHT * (v[0] - f.value)])
                case "y":
                    out.append([WEIGHT * (v[1] - f.value)])
                case "angle":
                    out.append([WEIGHT * math.sin(v[0] - f.value)])
                case "through":
                    normal = np.array([math.cos(v[0]), math.sin(v[0])])
                    out.append([WEIGHT * (float(normal @ np.asarray(f.point)) - v[1])])
        return np.concatenate([np.atleast_1d(np.asarray(r, dtype=np.float64)) for r in out])

    if not entities:
        return
    result = least_squares(
        residuals, np.array(x0, dtype=np.float64), method="lm", xtol=1e-12, ftol=1e-12
    )
    for eid, e in entities.items():
        v = unpack(result.x, eid)
        if isinstance(e, Line):
            e.angle, e.offset = float(v[0]), float(v[1])
        else:
            e.center, e.radius = v[:2].copy(), float(v[2])


def line_line(a: Line, b: Line, hint: FloatArray) -> FloatArray:
    m = np.array([a.normal, b.normal])
    if abs(np.linalg.det(m)) < 1e-3:
        return hint - (hint @ m[0] - a.offset) * m[0]
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
        return base
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    perp = np.array([-u[1], u[0]])
    options = [base + h * perp, base - h * perp]
    return min(options, key=lambda p: float(np.linalg.norm(p - hint)))


def intersect(a: Entity, b: Entity, hint: FloatArray, tangent: bool = False) -> FloatArray:
    """The junction of two consecutive entities closest to the hint."""
    if isinstance(a, Line) and isinstance(b, Line):
        return line_line(a, b, hint)
    if isinstance(a, Line):
        return line_circle(a, b.center, b.radius, hint, tangent)
    if isinstance(b, Line):
        return line_circle(b, a.center, a.radius, hint, tangent)
    return circle_circle(a.center, a.radius, b.center, b.radius, hint, tangent)


def project(entity: Entity, point: FloatArray) -> FloatArray:
    if isinstance(entity, Line):
        return point - (point @ entity.normal - entity.offset) * entity.normal
    direction = point - entity.center
    return entity.center + entity.radius * direction / max(float(np.linalg.norm(direction)), 1e-12)


def update_junctions(chains: Sequence[Chain], constraints: Sequence[Constraint]) -> None:
    """Exact shared endpoints, so consecutive entities meet without gaps."""
    tangent_pairs = {frozenset(c.refs) for c in constraints if c.kind == "tangent"}
    for chain in chains:
        n = len(chain.entities)
        if n == 1 and isinstance(chain.entities[0], Circle):
            continue
        for k in range(n if chain.closed else n - 1):
            a, b = chain.entities[k], chain.entities[(k + 1) % n]
            if isinstance(a, Circle) or isinstance(b, Circle):
                continue
            tangent = frozenset((a.id, b.id)) in tangent_pairs
            p = intersect(a, b, chain.junctions[k], tangent)
            a.end = p.copy()
            b.start = a.end
        if not chain.closed:
            first, last = chain.entities[0], chain.entities[-1]
            if not isinstance(first, Circle):
                first.start = project(first, chain.points[0][0])
            if not isinstance(last, Circle):
                last.end = project(last, chain.points[-1][-1])
