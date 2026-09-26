"""Constraint inference, the joint least-squares refit and exact junctions.

Methods: `.work/research/algorithms-cad.md` 1.6-1.7. The carriers of all fitted
entities (lines in normal form, circles) are refitted in one problem: point
residuals of their own section points, and heavily weighted residuals for
inferred constraints, snapped values, typed dimensions and pinned points. Shared
points are then computed from the carriers, never taken from the data, so
consecutive entities meet exactly.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    Entity,
    FixedValue,
    FloatArray,
    Line,
    WorkSketch,
    line_through,
)

WEIGHT = 1e4
MAX_POINTS_PER_ENTITY = 1000


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


# --------------------------------------------------------------------------- geometry


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


# --------------------------------------------------------------------------- inference


def _lines(sketch: WorkSketch) -> list[Line]:
    return [e for e in sketch.entities.values() if isinstance(e, Line) and e.origin == "fit"]


def _rounds(sketch: WorkSketch) -> list[Arc | Circle]:
    return [e for e in sketch.entities.values() if not isinstance(e, Line) and e.origin == "fit"]


def infer_constraints(sketch: WorkSketch, opts: ConstraintOptions) -> list[Constraint]:
    """A minimal, non-redundant constraint set for the fitted entities.

    Lines are grouped by direction: axis-parallel groups get horizontal/vertical,
    other groups one parallel chain, and two groups 90 degrees apart one
    perpendicular constraint. Tangency is tested by the gap, not by the measured
    junction angle, which is poorly defined at a tangent transition.
    """
    constraints: list[Constraint] = []
    groups: list[list[Line]] = []
    for line in sorted(_lines(sketch), key=direction_angle):
        if (
            groups
            and angle_gap(direction_angle(groups[-1][0]), direction_angle(line)) < opts.angle_tol
        ):
            groups[-1].append(line)
        else:
            groups.append([line])
    if (
        len(groups) > 1
        and angle_gap(direction_angle(groups[0][0]), direction_angle(groups[-1][0]))
        < opts.angle_tol
    ):
        groups[0] = groups.pop() + groups[0]

    free_groups: list[list[Line]] = []
    for group in groups:
        mean = direction_angle(group[0])
        if min(mean, math.pi - mean) < opts.angle_tol:
            constraints.extend(Constraint("horizontal", (line.id,)) for line in group)
            axis_parallel = True
        elif abs(mean - math.pi / 2) < opts.angle_tol:
            constraints.extend(Constraint("vertical", (line.id,)) for line in group)
            axis_parallel = True
        else:
            free_groups.append(group)
            axis_parallel = False
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
                continue
            if carriers and not axis_parallel:
                constraints.append(Constraint("parallel", (carriers[0].id, line.id)))
            carriers.append(line)

    for i, gi in enumerate(free_groups):
        for gj in free_groups[i + 1 :]:
            gap = angle_gap(direction_angle(gi[0]), direction_angle(gj[0]))
            if abs(gap - math.pi / 2) < opts.angle_tol:
                constraints.append(Constraint("perpendicular", (gi[0].id, gj[0].id)))

    rounds = _rounds(sketch)
    for a, b in itertools.pairwise(sorted(rounds, key=lambda e: e.radius)):
        if abs(a.radius - b.radius) < opts.radius_tol:
            constraints.append(Constraint("equalRadius", (a.id, b.id)))
    for i, a in enumerate(rounds):
        for b in rounds[i + 1 :]:
            if np.linalg.norm(a.center - b.center) < opts.center_tol:
                constraints.append(Constraint("concentric", (a.id, b.id)))

    for point_id, ends in sketch.incidence().items():
        if len(ends) != 2:
            continue
        (first, _), (second, _) = ends
        if first.origin != "fit" or second.origin != "fit":
            continue
        if isinstance(first, Line) and isinstance(second, Line):
            continue
        da = away_direction(sketch, first, point_id)
        db = away_direction(sketch, second, point_id)
        kink = math.acos(float(np.clip(-(da @ db), -1.0, 1.0)))
        if kink <= opts.tangent_angle_tol and tangent_gap(first, second) <= opts.tangent_gap:
            constraints.append(Constraint("tangent", (first.id, second.id)))
    return constraints


# --------------------------------------------------------------------------- solving


class _Layout:
    """Maps the carriers of the variable entities into one parameter vector."""

    def __init__(self, sketch: WorkSketch, variable: Iterable[str]) -> None:
        self.sketch = sketch
        self.slices: dict[str, slice] = {}
        values: list[float] = []
        for eid in variable:
            entity = sketch.entities[eid]
            start = len(values)
            values += (
                [entity.angle, entity.offset]
                if isinstance(entity, Line)
                else [*entity.center, entity.radius]
            )
            self.slices[eid] = slice(start, len(values))
        self.x0 = np.array(values, dtype=np.float64)

    def params(self, x: FloatArray, eid: str) -> FloatArray:
        """(angle, offset) or (cx, cy, r) of an entity; constants for non-variable entities."""
        part = self.slices.get(eid)
        if part is not None:
            return x[part]
        entity = self.sketch.entities[eid]
        if isinstance(entity, Line):
            return np.array([entity.angle, entity.offset])
        return np.array([*entity.center, entity.radius])

    def write_back(self, x: FloatArray) -> None:
        for eid, part in self.slices.items():
            entity = self.sketch.entities[eid]
            v = x[part]
            if isinstance(entity, Line):
                entity.angle, entity.offset = float(v[0]), float(v[1])
            else:
                entity.center, entity.radius = v[:2].copy(), float(v[2])


def _variable_entities(sketch: WorkSketch, fixed: Sequence[FixedValue]) -> list[str]:
    """Fitted carriers that have section points or fixed values to determine them."""
    anchored = {f.entity for f in fixed}
    result = []
    for eid, entity in sketch.entities.items():
        if entity.origin != "fit":
            continue
        count = len(sketch.samples_of(eid))
        if count >= (2 if isinstance(entity, Line) else 3) or eid in anchored:
            result.append(eid)
    return result


def _tangent_signs(
    sketch: WorkSketch, constraints: Sequence[Constraint]
) -> dict[tuple[str, ...], float]:
    """+1 for circles touching from outside, -1 from inside (chosen from the current fit)."""
    signs: dict[tuple[str, ...], float] = {}
    for c in constraints:
        if c.kind != "tangent":
            continue
        a, b = (sketch.entities[r] for r in c.refs)
        if isinstance(a, Line) or isinstance(b, Line):
            continue
        dist = float(np.linalg.norm(a.center - b.center))
        external = abs(dist - (a.radius + b.radius)) < abs(dist - abs(a.radius - b.radius))
        signs[c.refs] = 1.0 if external else -1.0
    return signs


def _constraint_residual(
    kind: str,
    v: list[FloatArray],
    refs: tuple[str, ...],
    sketch: WorkSketch,
    signs: dict[tuple[str, ...], float],
) -> list[float]:
    match kind:
        case "horizontal":
            return [math.cos(v[0][0])]
        case "vertical":
            return [math.sin(v[0][0])]
        case "parallel":
            return [math.sin(v[0][0] - v[1][0])]
        case "perpendicular":
            return [math.cos(v[0][0] - v[1][0])]
        case "collinear":
            delta = v[0][0] - v[1][0]
            return [math.sin(delta), v[1][1] * math.cos(delta) - v[0][1]]
        case "equalRadius":
            return [v[0][2] - v[1][2]]
        case "concentric":
            return [float(v[0][0] - v[1][0]), float(v[0][1] - v[1][1])]
        case "tangent":
            first, second = (sketch.entities[r] for r in refs)
            if isinstance(first, Line) or isinstance(second, Line):
                line, round_ = (v[0], v[1]) if isinstance(first, Line) else (v[1], v[0])
                normal = np.array([math.cos(line[0]), math.sin(line[0])])
                return [abs(float(round_[:2] @ normal) - line[1]) - round_[2]]
            gap = np.linalg.norm(v[0][:2] - v[1][:2]) - abs(v[0][2] + signs[refs] * v[1][2])
            return [float(gap)]
    raise ValueError(f"unknown constraint {kind}")


def _fixed_residual(value: FixedValue, v: FloatArray, is_line: bool) -> float:
    match value.kind:
        case "radius":
            return float(v[2] - value.value)
        case "x":
            return float(v[0] - value.value)
        case "y":
            return float(v[1] - value.value)
        case "angle":
            return math.sin(v[0] - value.value)
        case "through":
            p = np.asarray(value.point)
            if is_line:
                return float(np.array([math.cos(v[0]), math.sin(v[0])]) @ p - v[1])
            return float(np.linalg.norm(p - v[:2]) - v[2])
    raise ValueError(f"unhandled fixed value {value.kind}")


def _carrier(entity: Entity, v: FloatArray) -> Entity:
    """A copy of the entity with the carrier parameters `v` (for trial evaluations)."""
    if isinstance(entity, Line):
        return Line(entity.id, float(v[0]), float(v[1]), entity.start, entity.end, entity.origin)
    if isinstance(entity, Arc):
        return Arc(
            entity.id, v[:2], float(v[2]), entity.ccw, entity.start, entity.end, entity.origin
        )
    return Circle(entity.id, v[:2], float(v[2]), entity.origin)


def solve(
    sketch: WorkSketch,
    constraints: Sequence[Constraint],
    fixed: Sequence[FixedValue] = (),
) -> None:
    """Refit the carriers of all fitted entities, keeping constraints and fixed values.

    Entities that no constraint or fixed length ties together are independent, so each
    connected group is solved on its own: a section through a part with twenty buttons
    is twenty small problems instead of one large one.
    """
    fixed = [*fixed, *_pinned_points(sketch)]
    variable = _variable_entities(sketch, fixed)
    if not variable:
        return
    signs = _tangent_signs(sketch, constraints)
    variable_set = set(variable)
    active = [
        c
        for c in constraints
        if all(r in sketch.entities for r in c.refs) and variable_set.intersection(c.refs)
    ]
    for group in _solve_groups(sketch, variable, active, fixed):
        _solve_group(sketch, group, active, fixed, constraints, signs)


def _solve_groups(
    sketch: WorkSketch,
    variable: Sequence[str],
    active: Sequence[Constraint],
    fixed: Sequence[FixedValue],
) -> list[list[str]]:
    """Variable entities grouped by the constraints and fixed lengths that couple them."""
    parent = {eid: eid for eid in variable}

    def find(eid: str) -> str:
        while parent[eid] != eid:
            parent[eid] = parent[parent[eid]]
            eid = parent[eid]
        return eid

    def unite(ids: Iterable[str]) -> None:
        roots = [find(eid) for eid in ids if eid in parent]
        for root in roots[1:]:
            parent[root] = roots[0]

    for c in active:
        unite(c.refs)
    incidence = sketch.incidence()
    for value in fixed:
        entity = sketch.entities.get(value.entity)
        if value.kind != "length" or entity is None or isinstance(entity, Circle):
            continue
        # A length is measured between corner points, which depend on the neighbours.
        ends = (entity.start, entity.end)
        unite([entity.id, *(other.id for pid in ends for other, _ in incidence[pid])])
    groups: dict[str, list[str]] = {}
    for eid in variable:
        groups.setdefault(find(eid), []).append(eid)
    return list(groups.values())


type _Rows = Callable[[FloatArray], list[float]]


def _solve_group(
    sketch: WorkSketch,
    variable: Sequence[str],
    active: Sequence[Constraint],
    fixed: Sequence[FixedValue],
    all_constraints: Sequence[Constraint],
    signs: dict[tuple[str, ...], float],
) -> None:
    """Joint least-squares refit of one coupled group of entities."""
    layout = _Layout(sketch, variable)
    members = set(variable)
    samples = {}
    for eid in variable:
        points = sketch.samples_of(eid)
        if len(points) > MAX_POINTS_PER_ENTITY:
            points = points[np.linspace(0, len(points) - 1, MAX_POINTS_PER_ENTITY).astype(int)]
        samples[eid] = points
    tangent_pairs = {frozenset(c.refs) for c in all_constraints if c.kind == "tangent"}
    pinned = {pid for pid, p in sketch.points.items() if p.fixed}
    incidence = sketch.incidence()

    def columns(refs: Iterable[str]) -> list[int]:
        return [i for r in refs if r in layout.slices for i in _indices(layout.slices[r])]

    # Weighted rows (constraints, fixed values, lengths), each with the parameters it
    # reads, so the Jacobian differentiates every row only by its own columns.
    rows: list[tuple[_Rows, list[int]]] = []
    for c in active:
        if members.intersection(c.refs):
            rows.append((_constraint_rows(c, layout, sketch, signs), columns(c.refs)))
    for value in fixed:
        if value.entity in members and value.kind != "length":
            rows.append((_fixed_rows(value, layout, sketch), columns([value.entity])))
    for value in fixed:
        if value.entity in members and value.kind == "length":
            rows.append(
                (
                    _length_rows(value, layout, sketch, incidence, tangent_pairs, pinned),
                    list(range(len(layout.x0))),
                )
            )

    def point_residuals(x: FloatArray) -> list[FloatArray]:
        out = []
        for eid, points in samples.items():
            v = layout.params(x, eid)
            if isinstance(sketch.entities[eid], Line):
                out.append(points @ np.array([math.cos(v[0]), math.sin(v[0])]) - v[1])
            else:
                out.append(np.linalg.norm(points - v[:2], axis=1) - v[2])
        return out

    def weighted_residuals(x: FloatArray) -> FloatArray:
        return WEIGHT * np.asarray([r for evaluate, _ in rows for r in evaluate(x)], np.float64)

    def residuals(x: FloatArray) -> FloatArray:
        return np.concatenate([*point_residuals(x), weighted_residuals(x)])

    point_rows = sum(len(p) for p in samples.values())

    def jacobian(x: FloatArray) -> FloatArray:
        """Point rows analytically, weighted rows by forward differences over their columns."""
        bases = [np.asarray(evaluate(x), np.float64) for evaluate, _ in rows]
        jac = np.zeros((point_rows + sum(len(b) for b in bases), len(x)))
        row = 0
        for eid, points in samples.items():
            part = layout.slices[eid]
            v = x[part]
            block = jac[row : row + len(points)]
            if isinstance(sketch.entities[eid], Line):
                block[:, part.start] = points @ np.array([-math.sin(v[0]), math.cos(v[0])])
                block[:, part.start + 1] = -1.0
            else:
                delta = points - v[:2]
                rho = np.maximum(np.linalg.norm(delta, axis=1), 1e-12)
                block[:, part.start] = -delta[:, 0] / rho
                block[:, part.start + 1] = -delta[:, 1] / rho
                block[:, part.start + 2] = -1.0
            row += len(points)
        for (evaluate, cols), base in zip(rows, bases, strict=True):
            for column in cols:
                step = 1e-7 * max(1.0, abs(float(x[column])))
                shifted = x.copy()
                shifted[column] += step
                change = np.asarray(evaluate(shifted), np.float64) - base
                jac[row : row + len(base), column] = WEIGHT * change / step
            row += len(base)
        return jac

    count = len(residuals(layout.x0))
    method = "lm" if count >= len(layout.x0) else "trf"
    result = least_squares(
        residuals, layout.x0, jac=jacobian, method=method, xtol=1e-12, ftol=1e-12, gtol=1e-12
    )
    layout.write_back(result.x)


def _indices(part: slice) -> range:
    return range(part.start, part.stop)


def _constraint_rows(
    c: Constraint, layout: _Layout, sketch: WorkSketch, signs: dict[tuple[str, ...], float]
) -> _Rows:
    def rows(x: FloatArray) -> list[float]:
        carriers = [layout.params(x, r) for r in c.refs]
        return _constraint_residual(c.kind, carriers, c.refs, sketch, signs)

    return rows


def _fixed_rows(value: FixedValue, layout: _Layout, sketch: WorkSketch) -> _Rows:
    is_line = isinstance(sketch.entities[value.entity], Line)

    def rows(x: FloatArray) -> list[float]:
        return [_fixed_residual(value, layout.params(x, value.entity), is_line)]

    return rows


def _length_rows(
    value: FixedValue,
    layout: _Layout,
    sketch: WorkSketch,
    incidence: dict[str, list[tuple[Entity, str]]],
    tangent_pairs: set[frozenset[str]],
    pinned: set[str],
) -> _Rows:
    def rows(x: FloatArray) -> list[float]:
        trial = {eid: _carrier(e, layout.params(x, eid)) for eid, e in sketch.entities.items()}
        entity = trial[value.entity]
        assert not isinstance(entity, Circle)
        ends = [
            point_position(sketch, pid, trial, incidence, tangent_pairs, pinned)
            for pid in (entity.start, entity.end)
        ]
        return [float(np.linalg.norm(ends[1] - ends[0])) - value.value]

    return rows


def _pinned_points(sketch: WorkSketch) -> list[FixedValue]:
    """Every carrier through a point the user typed passes through it."""
    values = []
    for point_id, ends in sketch.incidence().items():
        point = sketch.points[point_id]
        if not point.fixed:
            continue
        for entity, _ in ends:
            if entity.origin == "fit":
                values.append(
                    FixedValue(entity.id, "through", point=(float(point.xy[0]), float(point.xy[1])))
                )
    return values


# --------------------------------------------------------------------------- junctions


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
