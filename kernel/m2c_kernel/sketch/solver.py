"""The joint least-squares refit of fitted sketch carriers.

Methods: `.work/research/algorithms-cad.md` 1.6-1.7. The carriers of all fitted
entities (lines in normal form, circles) are refitted in one problem per coupled
group: point residuals of their own section points, and heavily weighted residuals
for constraints, snapped values, typed dimensions and pinned points.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable, Sequence

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.sketch.carriers import point_position
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    Entity,
    FixedValue,
    FloatArray,
    Line,
    WorkSketch,
)

WEIGHT = 1e4
MAX_POINTS_PER_ENTITY = 1000


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
    only: Collection[str] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> None:
    """Refit the carriers of the fitted entities, keeping constraints and fixed values.

    With `only`, just these entities move; the others keep their carriers.

    Entities that no constraint or fixed length ties together are independent, so each
    connected group is solved on its own: a section through a part with twenty buttons
    is twenty small problems instead of one large one.
    """
    fixed = [*fixed, *_pinned_points(sketch)]
    variable = [e for e in _variable_entities(sketch, fixed) if only is None or e in only]
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
        if check_cancelled is not None:
            check_cancelled()
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
