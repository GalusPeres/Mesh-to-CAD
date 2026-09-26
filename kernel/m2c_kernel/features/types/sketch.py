"""Sketch: lines, arcs and circles on a plane, fitted to a section of the scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import StandardPlane, feature_refs, not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.wire import BlobRef

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class SketchPlaneRef:
    reference: StandardPlane | str
    """A standard plane or the id of a feature that provides a plane."""
    offset: float = 0.0
    x_direction: Vec3 | None = None
    flip: bool = False


@dataclass(frozen=True, kw_only=True)
class SectionSettings:
    mode: Literal["single", "stacked", "rotational"] = "single"
    count: int = 1
    spacing: float = 1.0
    axis: str | None = None
    """Axis feature of rotational sections."""
    offset: float = 0.0
    """Section position relative to the sketch plane."""
    faces: BlobRef | None = None
    """Restrict the section to these scan triangles."""


@dataclass(frozen=True, kw_only=True)
class SketchPoint:
    id: str
    x: float
    y: float


@dataclass(frozen=True, kw_only=True)
class LineEntity:
    type: Literal["line"] = "line"
    id: str
    start: str
    end: str


@dataclass(frozen=True, kw_only=True)
class ArcEntity:
    type: Literal["arc"] = "arc"
    id: str
    start: str
    end: str
    center: tuple[float, float]
    radius: float
    ccw: bool


@dataclass(frozen=True, kw_only=True)
class CircleEntity:
    type: Literal["circle"] = "circle"
    id: str
    center: tuple[float, float]
    radius: float


type SketchEntity = LineEntity | ArcEntity | CircleEntity

type ConstraintKind = Literal[
    "horizontal",
    "vertical",
    "parallel",
    "perpendicular",
    "collinear",
    "equalRadius",
    "concentric",
    "tangent",
]


@dataclass(frozen=True, kw_only=True)
class SketchConstraint:
    kind: ConstraintKind
    refs: list[str]


@dataclass(frozen=True, kw_only=True)
class SketchParams:
    plane: SketchPlaneRef
    section: SectionSettings = SectionSettings()
    tolerance: float | None = None
    """Fit tolerance in mm; None derives it from the section noise."""
    points: list[SketchPoint] = field(default_factory=list)
    entities: list[SketchEntity] = field(default_factory=list)
    loops: list[list[str]] = field(default_factory=list)
    constraints: list[SketchConstraint] = field(default_factory=list)


@feature_type("sketch", params=SketchParams, reads=ReadSet(mesh=True, settings=("tolerance",)))
class Sketch:
    @staticmethod
    def references(params: SketchParams) -> Refs:
        return Refs(features=feature_refs(params.plane.reference, params.section.axis))

    @staticmethod
    def evaluate(ctx: EvalContext, params: SketchParams) -> FeatureOutput:
        raise not_implemented("sketch")
