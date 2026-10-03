"""Closed loops, open chains and gaps of a sketch, and the nesting of its loops.

Loops are found from the shared points, never stored: a connected set of lines
and arcs whose points all join exactly two entity ends is a closed loop; any
point with a single end is a gap. A loop is named after its entity with the
lowest number, so its id survives edits elsewhere in the sketch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from m2c_kernel.sketch.fit2d import point_in_polygon, signed_area
from m2c_kernel.sketch.model import (
    Circle,
    Entity,
    FloatArray,
    WorkSketch,
    circle_points,
    entity_polyline,
)


@dataclass(frozen=True)
class Loop:
    id: str
    entities: tuple[str, ...]
    """In walking order."""
    reversed: tuple[bool, ...]
    """Per entity: walked from its end to its start."""
    polygon: FloatArray
    """Dense closed polygon along the loop (first point not repeated)."""

    @property
    def area(self) -> float:
        return signed_area(self.polygon)


@dataclass(frozen=True)
class Profile:
    loops: list[Loop] = field(default_factory=list)
    open_entities: list[str] = field(default_factory=list)
    gaps: list[FloatArray] = field(default_factory=list)
    """Positions of points where a chain ends."""
    branch_points: list[str] = field(default_factory=list)
    """Points where more than two entity ends meet."""

    @property
    def closed(self) -> bool:
        return bool(self.loops) and not self.open_entities


def entity_number(entity_id: str) -> tuple[int, str]:
    digits = entity_id[1:]
    return (int(digits), entity_id) if digits.isdigit() else (1 << 30, entity_id)


def analyse(sketch: WorkSketch) -> Profile:
    loops: list[Loop] = []
    open_entities: list[str] = []
    gaps: list[FloatArray] = []
    branches: list[str] = []
    for entity in sketch.entities.values():
        if isinstance(entity, Circle):
            loops.append(
                Loop(
                    entity.id,
                    (entity.id,),
                    (False,),
                    circle_points(entity.center, entity.radius)[:-1],
                )
            )
    incidence = sketch.incidence()
    seen: set[str] = set()
    for entity in sketch.entities.values():
        if isinstance(entity, Circle) or entity.id in seen:
            continue
        component = _component(sketch, entity, incidence)
        seen.update(e.id for e in component)
        points = {pid for e in component for pid in (e.start, e.end)}  # type: ignore[union-attr]
        degrees = {pid: len(incidence[pid]) for pid in points}
        branch = [pid for pid, d in degrees.items() if d > 2]
        ends = [pid for pid, d in degrees.items() if d == 1]
        if not branch and not ends:
            loop = _walk(sketch, component, incidence)
            if loop is not None:
                loops.append(loop)
                continue
        open_entities += [e.id for e in component]
        gaps += [sketch.xy(pid).copy() for pid in sorted(ends)]
        branches += sorted(branch)
    loops.sort(key=lambda loop: entity_number(loop.id))
    return Profile(loops, sorted(open_entities, key=entity_number), gaps, branches)


def _component(
    sketch: WorkSketch, first: Entity, incidence: dict[str, list[tuple[Entity, str]]]
) -> list[Entity]:
    found = {first.id: first}
    stack = [first]
    while stack:
        entity = stack.pop()
        assert not isinstance(entity, Circle)
        for pid in (entity.start, entity.end):
            for other, _ in incidence[pid]:
                if other.id not in found:
                    found[other.id] = other
                    stack.append(other)
    return list(found.values())


def _walk(
    sketch: WorkSketch, component: list[Entity], incidence: dict[str, list[tuple[Entity, str]]]
) -> Loop | None:
    """Order a cycle of entities; None if they do not form one simple cycle."""
    first = min(component, key=lambda e: entity_number(e.id))
    assert not isinstance(first, Circle)
    order: list[str] = []
    flipped: list[bool] = []
    parts: list[FloatArray] = []
    entity: Entity = first
    backwards = False
    for _ in range(len(component)):
        assert not isinstance(entity, Circle)
        order.append(entity.id)
        flipped.append(backwards)
        polyline = entity_polyline(sketch, entity)
        parts.append(polyline[::-1][:-1] if backwards else polyline[:-1])
        tip = entity.start if backwards else entity.end
        following = [(e, end) for e, end in incidence[tip] if e.id != entity.id]
        if len(following) != 1:
            return None
        entity, end = following[0]
        backwards = end == "end"
        if entity.id == first.id:
            break
    if entity.id != first.id or len(order) != len(component):
        return None
    return Loop(first.id, tuple(order), tuple(flipped), np.vstack(parts))


def nesting(loops: list[Loop]) -> list[tuple[int, list[int]]]:
    """Outer loops with their direct holes (even-odd nesting depth), as indices into `loops`."""
    containers = [
        [
            j
            for j, other in enumerate(loops)
            if j != i and point_in_polygon(loop.polygon[0], other.polygon)
        ]
        for i, loop in enumerate(loops)
    ]
    depth = [len(c) for c in containers]
    result: list[tuple[int, list[int]]] = []
    for i in range(len(loops)):
        if depth[i] % 2:
            continue
        holes = []
        for j in range(len(loops)):
            if depth[j] != depth[i] + 1:
                continue
            parent = min(containers[j], key=lambda k: abs(loops[k].area))
            if parent == i:
                holes.append(j)
        result.append((i, holes))
    return result
