"""Constraint inference: which relations the fitted entities of a sketch keep.

Methods: `.work/research/algorithms-cad.md` 1.6. Constraints are inferred within one
connected profile (entities that share points); equal values across separate
outlines come from value snapping with preferred values instead, which keeps every
outline its own small problem for the solver.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.sketch.carriers import angle_gap, away_direction, direction_angle, tangent_gap
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    Line,
    WorkSketch,
)


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


type Fitted = Line | Arc | Circle


def profiles(sketch: WorkSketch, only: Collection[str] | None = None) -> list[list[Fitted]]:
    """The fitted entities grouped into connected profiles (entities that share points)."""
    fitted = [
        e for e in sketch.entities.values() if e.origin == "fit" and (only is None or e.id in only)
    ]
    parent = {e.id: e.id for e in fitted}

    def find(eid: str) -> str:
        while parent[eid] != eid:
            parent[eid] = parent[parent[eid]]
            eid = parent[eid]
        return eid

    for ends in sketch.incidence().values():
        ids = [entity.id for entity, _ in ends if entity.id in parent]
        for other in ids[1:]:
            parent[find(other)] = find(ids[0])
    groups: dict[str, list[Fitted]] = {}
    for entity in fitted:
        groups.setdefault(find(entity.id), []).append(entity)
    return list(groups.values())


def infer_constraints(
    sketch: WorkSketch,
    opts: ConstraintOptions,
    only: Collection[str] | None = None,
    exclude: Collection[str] = (),
) -> list[Constraint]:
    """A minimal, non-redundant constraint set for the fitted entities.

    Within each connected profile, lines are grouped by direction: axis-parallel
    groups get horizontal/vertical, other groups one parallel chain, and two groups
    90 degrees apart one perpendicular constraint; arcs of equal radius are chained.
    Tangency is tested by the gap, not by the measured junction angle, which is poorly
    defined at a tangent transition. Across profiles only full circles of equal radius
    and concentric rounds are related.

    `only` limits the result to constraints on these entities (a new outline in an
    existing sketch); `exclude` entities (recognised shapes, which bring their own)
    get no profile constraints, only the relations across profiles.
    """
    chosen = [
        e for e in sketch.entities.values() if e.origin == "fit" and (only is None or e.id in only)
    ]
    inside = {e.id for e in chosen if e.id not in exclude}
    constraints: list[Constraint] = []
    for profile in profiles(sketch, inside):
        constraints += _line_constraints([e for e in profile if isinstance(e, Line)], opts)
        constraints += _equal_radii([e for e in profile if isinstance(e, Arc)], opts)
    rounds = [
        e for e in sketch.entities.values() if isinstance(e, Arc | Circle) and e.origin == "fit"
    ]
    related = [
        c
        for c in _equal_radii([e for e in rounds if isinstance(e, Circle)], opts)
        + _concentric(rounds, opts)
        if only is None or set(c.refs) & set(only)
    ]
    constraints += related + _tangents(sketch, opts, inside)
    unique: dict[tuple[str, frozenset[str]], Constraint] = {}
    for c in constraints:
        unique.setdefault((c.kind, frozenset(c.refs)), c)
    return list(unique.values())


def _concentric(rounds: Sequence[Arc | Circle], opts: ConstraintOptions) -> list[Constraint]:
    return [
        Constraint("concentric", (a.id, b.id))
        for i, a in enumerate(rounds)
        for b in rounds[i + 1 :]
        if np.linalg.norm(a.center - b.center) < opts.center_tol
    ]


def _equal_radii(rounds: Sequence[Arc | Circle], opts: ConstraintOptions) -> list[Constraint]:
    return [
        Constraint("equalRadius", (a.id, b.id))
        for a, b in itertools.pairwise(sorted(rounds, key=lambda e: e.radius))
        if abs(a.radius - b.radius) < opts.radius_tol
    ]


def _line_constraints(lines: Sequence[Line], opts: ConstraintOptions) -> list[Constraint]:
    constraints: list[Constraint] = []
    groups: list[list[Line]] = []
    for line in sorted(lines, key=direction_angle):
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
    return constraints


def _tangents(
    sketch: WorkSketch, opts: ConstraintOptions, only: Collection[str]
) -> list[Constraint]:
    constraints: list[Constraint] = []
    for point_id, ends in sketch.incidence().items():
        if len(ends) != 2:
            continue
        (first, _), (second, _) = ends
        if first.origin != "fit" or second.origin != "fit":
            continue
        if not (first.id in only and second.id in only):
            continue
        if isinstance(first, Line) and isinstance(second, Line):
            continue
        da = away_direction(sketch, first, point_id)
        db = away_direction(sketch, second, point_id)
        kink = math.acos(float(np.clip(-(da @ db), -1.0, 1.0)))
        if kink <= opts.tangent_angle_tol and tangent_gap(first, second) <= opts.tangent_gap:
            constraints.append(Constraint("tangent", (first.id, second.id)))
    return constraints
