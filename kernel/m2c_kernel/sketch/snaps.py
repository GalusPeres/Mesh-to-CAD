"""Design-intent value snapping of fitted sketch entities (through `snapping.py`).

Snapped are radii (equal radii share one value), positions of axis-parallel lines
and of free centres measured from the sketch origin, directions of oblique lines
and the corner where such a line meets an axis-parallel neighbour, and holes on
one bolt circle with equal pitch. Every snap becomes a fixed value of the joint
refit and is stored with the measurement it replaced, so the user can remove it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from m2c_kernel.sketch.constraints import direction_angle, intersect
from m2c_kernel.sketch.fit2d import fit_circle
from m2c_kernel.sketch.model import Circle, Constraint, FixedValue, Line, WorkSketch
from m2c_kernel.sketch.params import SketchSnap, SnapKind
from m2c_kernel.snapping import SnapUnits, snap_angle, snap_length

MIN_BOLT_HOLES = 3
BOLT_PITCH_TOL_DEG = 1.0


def _uncertainty(noise: float, count: int) -> float:
    return noise / math.sqrt(max(count, 1))


def _axis_of(line: Line) -> str | None:
    direction = direction_angle(line)
    if min(direction, math.pi - direction) < 1e-6:
        return "horizontal"
    if abs(direction - math.pi / 2) < 1e-6:
        return "vertical"
    return None


def fixed_values(sketch: WorkSketch, snap: SketchSnap) -> list[FixedValue]:
    """The residuals that keep a stored snap in a refit."""
    entity = sketch.entities.get(snap.entity)
    if entity is None:
        return []
    match snap.kind:
        case "radius":
            return [FixedValue(snap.entity, "radius", snap.value)]
        case "centerX":
            return [FixedValue(snap.entity, "x", snap.value)]
        case "centerY":
            return [FixedValue(snap.entity, "y", snap.value)]
        case "x" | "y" | "junction":
            point = snap.point or (0.0, 0.0)
            return [FixedValue(snap.entity, "through", point=point)]
        case "angle":
            if not isinstance(entity, Line):
                return []
            target = math.radians(snap.value) - math.pi / 2
            if math.cos(target - entity.angle) < 0:  # keep the normal orientation of the fit
                target += math.pi
            return [FixedValue(snap.entity, "angle", target)]
        case "boltCircle":
            return _bolt_fixed_values(snap)
    return []


def _bolt_positions(snap: SketchSnap) -> list[tuple[str, float, float]]:
    center = snap.point or (0.0, 0.0)
    radius = snap.value / 2
    start = math.radians(snap.start_deg or 0.0)
    pitch = math.radians(snap.pitch_deg or 0.0)
    return [
        (
            member,
            center[0] + radius * math.cos(start + k * pitch),
            center[1] + radius * math.sin(start + k * pitch),
        )
        for k, member in enumerate(snap.members)
    ]


def _bolt_fixed_values(snap: SketchSnap) -> list[FixedValue]:
    values = []
    for member, x, y in _bolt_positions(snap):
        values += [FixedValue(member, "x", x), FixedValue(member, "y", y)]
    return values


class _Collector:
    def __init__(self, rejected: Sequence[str]) -> None:
        self.rejected = set(rejected)
        self.snaps: list[SketchSnap] = []

    def add(
        self,
        entity: str,
        kind: SnapKind,
        value: float,
        measured: float,
        uncertainty: float,
        point: tuple[float, float] | None = None,
    ) -> bool:
        snap_id = f"{entity}:{kind}"
        if snap_id in self.rejected:
            return False
        self.snaps.append(
            SketchSnap(
                id=snap_id,
                entity=entity,
                kind=kind,
                value=value,
                measured=measured,
                uncertainty=uncertainty,
                point=point,
            )
        )
        return True


def find_snaps(
    sketch: WorkSketch,
    constraints: Sequence[Constraint],
    noise: float,
    units: SnapUnits,
    rejected: Sequence[str] = (),
) -> list[SketchSnap]:
    """Snaps of the current (constrained, refitted) entities."""
    floor = max(0.01, 2.0 * noise)
    tangent = {r for c in constraints if c.kind == "tangent" for r in c.refs}
    out = _Collector(rejected)
    bolted = _bolt_circles(sketch, noise, units, floor, out)
    radii: list[float] = []
    fitted = [e for e in sketch.entities.values() if e.origin == "fit"]
    for entity in fitted:
        count = len(sketch.samples_of(entity.id))
        if count == 0:
            continue
        u = _uncertainty(noise, count)
        if isinstance(entity, Line):
            _snap_line(sketch, entity, u, units, floor, out)
            continue
        snap = snap_length(entity.radius, u, units=units, floor=floor, preferred=radii)
        if snap is not None and out.add(entity.id, "radius", snap.value, entity.radius, u):
            radii.append(snap.value)
        if entity.id in tangent or entity.id in bolted:
            continue
        for index, kind in ((0, "centerX"), (1, "centerY")):
            measured = float(entity.center[index])
            center = snap_length(measured, u, units=units, floor=floor)
            if center is not None:
                out.add(entity.id, kind, center.value, measured, u)  # type: ignore[arg-type]
    _snap_junctions(sketch, noise, units, floor, out)
    return out.snaps


def _snap_line(
    sketch: WorkSketch, line: Line, u: float, units: SnapUnits, floor: float, out: _Collector
) -> None:
    axis = _axis_of(line)
    start, end = sketch.xy(line.start), sketch.xy(line.end)
    middle = 0.5 * (start + end)
    if axis is not None:
        along = 1 if axis == "horizontal" else 0
        measured = float(line.offset * line.normal[along])
        snap = snap_length(measured, u, units=units, floor=floor)
        if snap is not None:
            point = (float(middle[0]), snap.value) if along == 1 else (snap.value, float(middle[1]))
            out.add(line.id, "y" if along == 1 else "x", snap.value, measured, u, point)
        return
    length = max(float(np.linalg.norm(end - start)), 1e-6)
    u_deg = math.degrees(u / length * math.sqrt(12.0))
    direction = math.degrees(direction_angle(line))
    angle = snap_angle(direction, u_deg)
    if angle is not None:
        out.add(line.id, "angle", angle.value, direction, u_deg)


def _snap_junctions(
    sketch: WorkSketch, noise: float, units: SnapUnits, floor: float, out: _Collector
) -> None:
    """Corners of oblique lines with a snapped angle on a snapped axis-parallel neighbour."""
    angled = {s.entity for s in out.snaps if s.kind == "angle"}
    placed = {s.entity: s for s in out.snaps if s.kind in ("x", "y")}
    done: set[str] = set()
    for point_id, ends in sketch.incidence().items():
        if len(ends) != 2:
            continue
        (a, _), (b, _) = ends
        for line, neighbour in ((a, b), (b, a)):
            if line.id not in angled or line.id in done or neighbour.id not in placed:
                continue
            if not isinstance(line, Line) or not isinstance(neighbour, Line):
                continue
            corner = intersect(line, neighbour, sketch.xy(point_id))
            position = placed[neighbour.id]
            along = 0 if position.kind == "y" else 1
            u = 2.0 * _uncertainty(noise, len(sketch.samples_of(line.id)))
            snap = snap_length(float(corner[along]), u, units=units, floor=floor)
            if snap is None:
                continue
            point = [0.0, 0.0]
            point[along] = snap.value
            point[1 - along] = position.value
            if out.add(
                line.id, "junction", snap.value, float(corner[along]), u, (point[0], point[1])
            ):
                done.add(line.id)


def _bolt_circles(
    sketch: WorkSketch, noise: float, units: SnapUnits, floor: float, out: _Collector
) -> set[str]:
    """Circles of equal radius whose centres lie on one circle with equal angular pitch."""
    circles = sorted(
        (e for e in sketch.entities.values() if isinstance(e, Circle) and e.origin == "fit"),
        key=lambda e: e.radius,
    )
    groups: list[list[Circle]] = []
    for circle in circles:
        if groups and abs(groups[-1][0].radius - circle.radius) < max(floor, 0.05):
            groups[-1].append(circle)
        else:
            groups.append([circle])
    members: set[str] = set()
    for group in groups:
        if len(group) < MIN_BOLT_HOLES:
            continue
        centers = np.array([c.center for c in group])
        pattern = fit_circle(centers) if len(group) >= 3 else None
        if pattern is None or pattern.max_error > max(floor, 0.05) or pattern.radius > 1e4:
            continue
        rel = centers - pattern.center
        angles = np.degrees(np.arctan2(rel[:, 1], rel[:, 0]))
        order = np.argsort(angles)
        angles, group = angles[order], [group[i] for i in order]
        gaps = np.diff(np.append(angles, angles[0] + 360.0))
        n = len(group)
        if np.all(np.abs(gaps - 360.0 / n) < BOLT_PITCH_TOL_DEG):
            pitch, first = 360.0 / n, 0
        else:
            # Partial pattern: the largest gap is the opening; the pitch is the rest.
            opening = int(np.argmax(gaps))
            inner = np.delete(gaps, opening)
            if np.ptp(inner) > BOLT_PITCH_TOL_DEG:
                continue
            pitch_snap = snap_angle(float(inner.mean()), BOLT_PITCH_TOL_DEG / 3)
            if pitch_snap is None:
                continue
            pitch, first = pitch_snap.value, (opening + 1) % n
        ordered = group[first:] + group[:first]
        start_measured = float(angles[first])
        u_center = _uncertainty(noise, sum(len(sketch.samples_of(c.id)) for c in group))
        cx = snap_length(float(pattern.center[0]), u_center, units=units, floor=floor)
        cy = snap_length(float(pattern.center[1]), u_center, units=units, floor=floor)
        diameter = snap_length(2 * pattern.radius, 2 * u_center, units=units, floor=floor)
        start = snap_angle(
            start_measured % 360.0, BOLT_PITCH_TOL_DEG / 3, candidates=_start_angles(pitch)
        )
        if cx is None or cy is None or diameter is None:
            continue
        snap_id = f"{ordered[0].id}:boltCircle"
        if snap_id in out.rejected:
            continue
        out.snaps.append(
            SketchSnap(
                id=snap_id,
                entity=ordered[0].id,
                kind="boltCircle",
                value=diameter.value,
                measured=2 * pattern.radius,
                uncertainty=2 * u_center,
                point=(cx.value, cy.value),
                members=[c.id for c in ordered],
                pitch_deg=pitch,
                start_deg=start.value if start is not None else start_measured,
            )
        )
        members.update(c.id for c in ordered)
    return members


def _start_angles(pitch: float) -> list[float]:
    base = [0.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0, 180.0]
    return sorted({a % 360.0 for a in base + [a + 180.0 for a in base] + [a - pitch for a in base]})
