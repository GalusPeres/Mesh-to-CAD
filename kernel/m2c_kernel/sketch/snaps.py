"""Design-intent value snapping of fitted sketch entities (through `snapping.py`).

Snapped are radii (equal radii share one value), positions of axis-parallel lines
and of free centres measured from the sketch origin, angles of oblique lines and
the position of their junction with an axis-parallel neighbour. Every snap becomes
a fixed value of the joint refit and is reported, so the user can remove it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.sketch.constraints import intersect
from m2c_kernel.sketch.model import Chain, Constraint, Entity, FixedValue, Line
from m2c_kernel.snapping import SnapUnits, snap_angle, snap_length


@dataclass(frozen=True)
class SnapRecord:
    id: str
    """Stable id `<entity>:<kind>`; rejected snaps are passed back by id."""
    entity: str
    kind: str
    value: float
    measured: float
    uncertainty: float
    fixed: FixedValue


def _uncertainty(noise: float, points: int) -> float:
    return noise / math.sqrt(max(points, 1))


def _axis(line: Line) -> str | None:
    direction = (line.angle + math.pi / 2) % math.pi
    if min(direction, math.pi - direction) < 1e-6:
        return "horizontal"
    if abs(direction - math.pi / 2) < 1e-6:
        return "vertical"
    return None


def find_snaps(
    chains: Sequence[Chain],
    constraints: Sequence[Constraint],
    noise: float,
    units: SnapUnits,
    rejected: Sequence[str] = (),
) -> list[SnapRecord]:
    """Snaps of the current (constrained, refitted) entities."""
    floor = max(0.01, 2.0 * noise)
    rejected_ids = set(rejected)
    tangent = {r for c in constraints if c.kind == "tangent" for r in c.refs}
    records: list[SnapRecord] = []
    points = {e.id: p for c in chains for e, p in zip(c.entities, c.points, strict=True)}
    raw_count = {eid: len(p) for eid, p in points.items()}

    def add(
        entity: Entity,
        kind: str,
        measured: float,
        uncertainty: float,
        fixed: FixedValue,
        value: float | None = None,
    ) -> None:
        snap_id = f"{entity.id}:{kind}"
        if snap_id in rejected_ids:
            return
        shown = fixed.value if value is None else value
        records.append(SnapRecord(snap_id, entity.id, kind, shown, measured, uncertainty, fixed))

    radii: list[float] = []
    lines_by_id: dict[str, Line] = {}
    for chain in chains:
        for entity in chain.entities:
            count = raw_count[entity.id]
            if isinstance(entity, Line):
                lines_by_id[entity.id] = entity
                axis = _axis(entity)
                u = _uncertainty(noise, count)
                if axis is not None:
                    coordinate = 1 if axis == "horizontal" else 0
                    measured = float(entity.offset * entity.normal[coordinate])
                    snap = snap_length(measured, u, units=units, floor=floor)
                    if snap is not None:
                        point = (0.0, snap.value) if coordinate == 1 else (snap.value, 0.0)
                        kind = "y" if coordinate == 1 else "x"
                        add(entity, kind, measured, u, FixedValue(entity.id, "through", snap.value, point))
                else:
                    direction = math.degrees((entity.angle + math.pi / 2) % math.pi)
                    length = max(float(np.linalg.norm(entity.end - entity.start)), 1e-6)
                    u_deg = math.degrees(noise / length * math.sqrt(12.0 / max(count, 1)))
                    angle = snap_angle(direction, u_deg)
                    if angle is not None:
                        target = math.radians(angle.value) - math.pi / 2
                        # keep the normal orientation of the fit
                        if math.cos(target - entity.angle) < 0:
                            target += math.pi
                        add(
                            entity,
                            "angle",
                            direction,
                            u_deg,
                            FixedValue(entity.id, "angle", target),
                            angle.value,
                        )
                continue
            u = _uncertainty(noise, count)
            snap = snap_length(entity.radius, u, units=units, floor=floor, preferred=radii)
            if snap is not None:
                radii.append(snap.value)
                add(entity, "radius", entity.radius, u, FixedValue(entity.id, "radius", snap.value))
            if entity.id in tangent:
                continue
            for index, kind in ((0, "x"), (1, "y")):
                center = snap_length(float(entity.center[index]), u, units=units, floor=floor)
                if center is not None:
                    fixed_kind = "x" if index == 0 else "y"
                    add(
                        entity,
                        f"center{kind.upper()}",
                        float(entity.center[index]),
                        u,
                        FixedValue(entity.id, fixed_kind, center.value),
                    )

    # oblique lines with a snapped angle: snap their junction with an axis-parallel neighbour
    snapped_angles = {r.entity for r in records if r.kind == "angle"}
    positions = {r.entity: r.fixed for r in records if r.fixed.kind == "through"}
    for chain in chains:
        n = len(chain.entities)
        for k, entity in enumerate(chain.entities):
            if entity.id not in snapped_angles or not isinstance(entity, Line):
                continue
            neighbours = []
            if chain.closed or k > 0:
                neighbours.append(chain.entities[(k - 1) % n])
            if chain.closed or k < n - 1:
                neighbours.append(chain.entities[(k + 1) % n])
            for neighbour in neighbours:
                if not isinstance(neighbour, Line) or neighbour.id not in positions:
                    continue
                axis = _axis(neighbour)
                junction = intersect(entity, neighbour, entity.start)
                along = 0 if axis == "horizontal" else 1
                u = _uncertainty(noise, raw_count[entity.id]) * 2.0
                snap = snap_length(float(junction[along]), u, units=units, floor=floor)
                if snap is None:
                    continue
                point = [0.0, 0.0]
                point[along] = snap.value
                point[1 - along] = positions[neighbour.id].value
                add(
                    entity,
                    "junction",
                    float(junction[along]),
                    u,
                    FixedValue(entity.id, "through", snap.value, (point[0], point[1])),
                )
                break
    return records
