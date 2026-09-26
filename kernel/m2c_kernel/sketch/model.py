"""Working model of a sketch during fitting and refitting.

Entities keep their carrier (a line in normal form, a circle) as the solved
quantity; their ends are shared points, computed from the carriers after each
solve so that consecutive entities meet exactly. `convert.py` turns this model
into the stored `SketchParams` and back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

type FloatArray = npt.NDArray[np.float64]
type Origin = Literal["fit", "drawn", "axis"]


def _empty() -> FloatArray:
    return np.zeros((0, 2))


@dataclass
class Point:
    id: str
    xy: FloatArray
    fixed: bool = False


@dataclass
class Line:
    id: str
    angle: float
    """Normal angle: the carrier is {p : (cos, sin) . p = offset}."""
    offset: float
    start: str
    end: str
    origin: Origin = "fit"
    kind: Literal["line"] = "line"

    @property
    def normal(self) -> FloatArray:
        return np.array([math.cos(self.angle), math.sin(self.angle)])

    @property
    def direction(self) -> FloatArray:
        return np.array([-math.sin(self.angle), math.cos(self.angle)])


@dataclass
class Arc:
    id: str
    center: FloatArray
    radius: float
    ccw: bool
    start: str
    end: str
    origin: Origin = "fit"
    kind: Literal["arc"] = "arc"


@dataclass
class Circle:
    id: str
    center: FloatArray
    radius: float
    origin: Origin = "fit"
    kind: Literal["circle"] = "circle"


type Entity = Line | Arc | Circle
type Curved = Arc | Circle


@dataclass(frozen=True)
class Constraint:
    kind: Literal[
        "horizontal",
        "vertical",
        "parallel",
        "perpendicular",
        "collinear",
        "equalRadius",
        "concentric",
        "tangent",
    ]
    refs: tuple[str, ...]


type FixedKind = Literal["radius", "x", "y", "angle", "through", "length"]


@dataclass(frozen=True)
class FixedValue:
    """A value the joint refit keeps (a heavily weighted residual).

    - `radius`, `x`, `y`: radius and centre coordinates of an arc or circle.
    - `angle`: normal angle of a line in radians.
    - `through`: the carrier passes through `point`.
    - `length`: distance between the two end points of a line.
    """

    entity: str
    kind: FixedKind
    value: float = 0.0
    point: tuple[float, float] = (0.0, 0.0)


@dataclass
class WorkSketch:
    points: dict[str, Point] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    samples: dict[str, FloatArray] = field(default_factory=dict)
    """Section points per fitted entity."""
    constraints: list[Constraint] = field(default_factory=list)

    def incidence(self) -> dict[str, list[tuple[Entity, str]]]:
        """For every point, the entity ends (`start` or `end`) that meet there."""
        table: dict[str, list[tuple[Entity, str]]] = {pid: [] for pid in self.points}
        for entity in self.entities.values():
            if isinstance(entity, Circle):
                continue
            table[entity.start].append((entity, "start"))
            table[entity.end].append((entity, "end"))
        return table

    def xy(self, point_id: str) -> FloatArray:
        return self.points[point_id].xy

    def samples_of(self, entity_id: str) -> FloatArray:
        return self.samples.get(entity_id, _empty())


def arc_angles(
    center: FloatArray, start: FloatArray, end: FloatArray, ccw: bool
) -> tuple[float, float]:
    """Start angle and signed sweep of an arc (a full turn if its ends coincide)."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
    if abs(sweep) < 1e-9:
        sweep = 2 * math.pi if ccw else -2 * math.pi
    return a0, sweep


def arc_points(
    center: FloatArray,
    radius: float,
    start: FloatArray,
    end: FloatArray,
    ccw: bool,
    step_deg: float = 3.0,
) -> FloatArray:
    a0, sweep = arc_angles(center, start, end, ccw)
    count = max(8, math.ceil(abs(sweep) / math.radians(step_deg)))
    t = a0 + np.linspace(0.0, sweep, count + 1)
    return np.column_stack([center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)])


def circle_points(center: FloatArray, radius: float, step_deg: float = 3.0) -> FloatArray:
    count = max(16, math.ceil(360.0 / step_deg))
    t = np.linspace(0.0, 2 * math.pi, count + 1)
    return np.column_stack([center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)])


def arc_midpoint(
    center: FloatArray, radius: float, start: FloatArray, end: FloatArray, ccw: bool
) -> FloatArray:
    a0, sweep = arc_angles(center, start, end, ccw)
    a = a0 + sweep / 2
    return center + radius * np.array([math.cos(a), math.sin(a)])


def segment_distances(points: FloatArray, a: FloatArray, b: FloatArray) -> FloatArray:
    """Distances of points to the segment a-b."""
    d = b - a
    length_sq = float(d @ d)
    if length_sq < 1e-24:
        result: FloatArray = np.linalg.norm(points - a, axis=1)
        return result
    t = np.clip((points - a) @ d / length_sq, 0.0, 1.0)
    result = np.linalg.norm(points - (a + t[:, None] * d), axis=1)
    return result


def arc_distances(
    points: FloatArray,
    center: FloatArray,
    radius: float,
    start: FloatArray,
    end: FloatArray,
    ccw: bool,
) -> FloatArray:
    """Distances of points to an arc: radial inside its sweep, to the nearer end outside."""
    a0, sweep = arc_angles(center, start, end, ccw)
    rel = points - center
    angle = np.arctan2(rel[:, 1], rel[:, 0])
    along = (angle - a0) % (2 * math.pi) if sweep > 0 else (a0 - angle) % (2 * math.pi)
    inside = along <= abs(sweep)
    radial = np.abs(np.linalg.norm(rel, axis=1) - radius)
    to_ends = np.minimum(
        np.linalg.norm(points - start, axis=1), np.linalg.norm(points - end, axis=1)
    )
    result: FloatArray = np.where(inside, radial, to_ends)
    return result


def entity_distances(sketch: WorkSketch, entity: Entity, points: FloatArray) -> FloatArray:
    """Distances of points to the finite entity (segment, arc or circle)."""
    if isinstance(entity, Circle):
        result: FloatArray = np.abs(np.linalg.norm(points - entity.center, axis=1) - entity.radius)
        return result
    start, end = sketch.xy(entity.start), sketch.xy(entity.end)
    if isinstance(entity, Line):
        return segment_distances(points, start, end)
    return arc_distances(points, entity.center, entity.radius, start, end, entity.ccw)


def carrier_distances(entity: Entity, points: FloatArray) -> FloatArray:
    """Distances of points to the infinite carrier (line or full circle)."""
    if isinstance(entity, Line):
        result: FloatArray = np.abs(points @ entity.normal - entity.offset)
        return result
    result = np.abs(np.linalg.norm(points - entity.center, axis=1) - entity.radius)
    return result


def entity_polyline(sketch: WorkSketch, entity: Entity) -> FloatArray:
    if isinstance(entity, Circle):
        return circle_points(entity.center, entity.radius)
    start, end = sketch.xy(entity.start), sketch.xy(entity.end)
    if isinstance(entity, Line):
        return np.vstack([start, end])
    return arc_points(entity.center, entity.radius, start, end, entity.ccw)


def line_through(a: FloatArray, b: FloatArray) -> tuple[float, float]:
    """Normal angle and offset of the line through two points (direction from a to b)."""
    d = b - a
    angle = math.atan2(-d[0], d[1])
    normal = np.array([math.cos(angle), math.sin(angle)])
    return angle, float(normal @ a)
