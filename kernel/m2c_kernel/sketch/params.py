"""Stored form of a sketch: where it lies, and its points, entities and constraints.

All coordinates are millimetres in the sketch plane frame (u along the frame's X
direction, v along its Y direction). Lines and arcs share their end points by id,
so a closed profile has no gaps by construction. The stored entities are
authoritative: a rebuild draws and extrudes them as they are and only compares
them with the current section of the scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from m2c_kernel.features.common import StandardAxis, StandardPlane
from m2c_kernel.geometry import Vec3

# --------------------------------------------------------------------------- where


@dataclass(frozen=True, kw_only=True)
class StandardPlaneSource:
    type: Literal["standard"] = "standard"
    plane: StandardPlane


@dataclass(frozen=True, kw_only=True)
class FeaturePlaneSource:
    """The plane of a fit or reference feature."""

    type: Literal["feature"] = "feature"
    feature: str


@dataclass(frozen=True, kw_only=True)
class AxisNormalSource:
    """The plane perpendicular to an axis, through the axis point nearest the origin."""

    type: Literal["axisNormal"] = "axisNormal"
    axis: StandardAxis | str
    """A global axis or a feature that provides an axis (cylinder, cone, torus, axis)."""


type PlaneSource = StandardPlaneSource | FeaturePlaneSource | AxisNormalSource


@dataclass(frozen=True, kw_only=True)
class PlanarSection:
    """A sketch on a plane; the scan is cut parallel to it and projected onto it."""

    type: Literal["planar"] = "planar"
    plane: PlaneSource
    offset: float = 0.0
    """Sketch plane position along the normal of the source plane."""
    section_offset: float = 0.0
    """Position of the cut relative to the sketch plane."""
    x_direction: Vec3 | None = None
    """In-plane X direction; by default the global X (or Y) axis projected into the plane."""
    flip: bool = False
    """Reverse the normal (the in-plane Y direction follows)."""


@dataclass(frozen=True, kw_only=True)
class RotationalSection:
    """A profile in the half-plane through an axis; scan points of all angles fold into it.

    Sketch X runs along the axis, sketch Y is the distance from the axis.
    """

    type: Literal["rotational"] = "rotational"
    axis: StandardAxis | str
    angle_deg: float = 0.0
    """Direction of the half-plane about the axis, from the global Z (or X) direction."""


type SketchSection = PlanarSection | RotationalSection

# --------------------------------------------------------------------------- geometry

type EntityOrigin = Literal["fit", "drawn", "axis"]
"""`fit` entities follow the section in refits, `drawn` ones are user geometry and
`axis` lines close rotational profiles along the axis (v = 0)."""


@dataclass(frozen=True, kw_only=True)
class SketchPoint:
    id: str
    x: float
    y: float
    fixed: bool = False
    """Typed by the user; refits keep the point where it is."""


@dataclass(frozen=True, kw_only=True)
class LineEntity:
    type: Literal["line"] = "line"
    id: str
    start: str
    end: str
    origin: EntityOrigin = "fit"


@dataclass(frozen=True, kw_only=True)
class ArcEntity:
    type: Literal["arc"] = "arc"
    id: str
    start: str
    end: str
    center: tuple[float, float]
    radius: float
    ccw: bool
    origin: EntityOrigin = "fit"


@dataclass(frozen=True, kw_only=True)
class CircleEntity:
    type: Literal["circle"] = "circle"
    id: str
    center: tuple[float, float]
    radius: float
    origin: EntityOrigin = "fit"


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


type SnapKind = Literal["radius", "x", "y", "angle", "centerX", "centerY", "junction", "boltCircle"]


@dataclass(frozen=True, kw_only=True)
class SketchSnap:
    """A design value applied by snapping, with the measurement it replaced.

    `x` and `y` place an axis-parallel line, `angle` is the direction of an oblique
    line in degrees, `junction` places the corner of an oblique line on its snapped
    neighbour (`point`). `boltCircle` places the circles `members` on a circle of
    diameter `value` around `point`, starting at `start_deg` with `pitch_deg`.
    The id `<entity>:<kind>` is stable, so a removed snap stays removed
    (`rejected_snaps`).
    """

    id: str
    entity: str
    kind: SnapKind
    value: float
    measured: float
    uncertainty: float
    point: tuple[float, float] | None = None
    members: list[str] = field(default_factory=list)
    pitch_deg: float | None = None
    start_deg: float | None = None


type DimensionKind = Literal["length", "angle", "radius", "centerX", "centerY"]


@dataclass(frozen=True, kw_only=True)
class SketchDimension:
    """A value typed by the user; refits keep it exactly (angle in degrees)."""

    entity: str
    kind: DimensionKind
    value: float


@dataclass(frozen=True, kw_only=True)
class SketchParams:
    section: SketchSection
    tolerance: float | None = None
    """Fit tolerance in mm; None derives it from `noise` (max(6 sigma, 0.05 mm))."""
    noise: float | None = None
    """Scan noise measured on the section by the last automatic fit."""
    points: list[SketchPoint] = field(default_factory=list)
    entities: list[SketchEntity] = field(default_factory=list)
    constraints: list[SketchConstraint] = field(default_factory=list)
    snaps: list[SketchSnap] = field(default_factory=list)
    dimensions: list[SketchDimension] = field(default_factory=list)
    rejected_snaps: list[str] = field(default_factory=list)
