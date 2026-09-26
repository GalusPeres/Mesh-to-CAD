"""Working model of a fitted sketch: mutable 2D entities with their source points.

The fitting pipeline refines these objects in place; `to_params` turns them into
the stored, authoritative `SketchParams` with shared junction points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

type FloatArray = npt.NDArray[np.float64]


def _zeros() -> FloatArray:
    return np.zeros(2)


@dataclass
class Line:
    id: str
    angle: float
    """Normal angle: the line is {p : (cos, sin) . p = offset}."""
    offset: float
    start: FloatArray = field(default_factory=_zeros)
    end: FloatArray = field(default_factory=_zeros)
    kind: Literal["line"] = "line"

    @property
    def normal(self) -> FloatArray:
        return np.array([math.cos(self.angle), math.sin(self.angle)])

    def distances(self, points: FloatArray) -> FloatArray:
        """Distances of points to the segment between start and end."""
        return segment_distances(points, self.start, self.end)


@dataclass
class Arc:
    id: str
    center: FloatArray
    radius: float
    ccw: bool
    start: FloatArray = field(default_factory=_zeros)
    end: FloatArray = field(default_factory=_zeros)
    kind: Literal["arc"] = "arc"

    def distances(self, points: FloatArray) -> FloatArray:
        result: FloatArray = np.abs(np.linalg.norm(points - self.center, axis=1) - self.radius)
        return result


@dataclass
class Circle:
    id: str
    center: FloatArray
    radius: float
    kind: Literal["circle"] = "circle"

    def distances(self, points: FloatArray) -> FloatArray:
        result: FloatArray = np.abs(np.linalg.norm(points - self.center, axis=1) - self.radius)
        return result


type Entity = Line | Arc | Circle


@dataclass
class Chain:
    """Entities of one section polyline in traversal order."""

    entities: list[Entity]
    points: list[FloatArray]
    """Section samples per entity (for refits and deviations)."""
    junctions: list[FloatArray]
    """Measured junction between entity k and k + 1 (closed chains wrap around)."""
    closed: bool


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


@dataclass(frozen=True)
class FixedValue:
    """A snapped value the joint refit keeps (a penalty residual)."""

    entity: str
    kind: Literal["radius", "x", "y", "angle", "through"]
    value: float
    point: tuple[float, float] = (0.0, 0.0)
    """For `through`: the line passes through this point."""


def segment_distances(points: FloatArray, a: FloatArray, b: FloatArray) -> FloatArray:
    d = b - a
    length_sq = float(d @ d)
    if length_sq < 1e-24:
        result: FloatArray = np.linalg.norm(points - a, axis=1)
        return result
    t = np.clip((points - a) @ d / length_sq, 0.0, 1.0)
    result = np.linalg.norm(points - (a + t[:, None] * d), axis=1)
    return result


def arc_polyline(
    center: FloatArray, radius: float, start: FloatArray, end: FloatArray, ccw: bool
) -> FloatArray:
    """Points along an arc from start to end (a full circle if they coincide)."""
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
    if abs(sweep) < 1e-9:
        sweep = 2 * math.pi if ccw else -2 * math.pi
    count = max(8, int(abs(sweep) / math.radians(3.0)))
    t = a0 + np.linspace(0.0, sweep, count + 1)
    return np.column_stack([center[0] + radius * np.cos(t), center[1] + radius * np.sin(t)])


def entity_polyline(entity: Entity) -> FloatArray:
    if isinstance(entity, Line):
        return np.vstack([entity.start, entity.end])
    if isinstance(entity, Arc):
        return arc_polyline(entity.center, entity.radius, entity.start, entity.end, entity.ccw)
    start = entity.center + np.array([entity.radius, 0.0])
    return arc_polyline(entity.center, entity.radius, start, start, True)
