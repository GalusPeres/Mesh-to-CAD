"""Reference geometry: planes and axes constructed from other features.

Inputs are origin planes (`XY`, `YZ`, `XZ`), origin axes (`X`, `Y`, `Z`), fit
features and other reference features. A plane input is a fitted plane or a
reference plane; an axis input is the axis of a fitted cylinder, cone or torus
or a reference axis.

`planeThroughAxis` contains the axis and is rotated by `angle_deg` about it,
counter-clockwise seen from the tip of the axis. At 0 degrees it also contains
the X direction, or the Y direction for axes within 45 degrees of X (projected
perpendicular to the axis): about Z, 0 degrees gives the XZ plane and 90
degrees the YZ plane. The rule is stable for axes that are nearly parallel to a
global axis, which fitted axes usually are.

The drawn size follows the scan: planes are squares and axes segments centred
near the middle of the scan. Statistics carry the geometry for the panels:
`pointX/Y/Z` and `directionX/Y/Z` (plane origin and normal, or axis point and
direction), and for planes `xDirX/Y/Z`, the first edge direction of the square.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.reference import ErrorCode
from m2c_kernel.document.results import Construction, DisplaySource, FeatureOutput
from m2c_kernel.features.common import StandardAxis, StandardPlane, feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.api import (
    GLOBAL_AXES,
    Axis,
    Cone,
    Cylinder,
    Plane,
    Torus,
    angle_to_axis_deg,
    axis_segment,
    plane_patch,
)
from m2c_kernel.geometry import FloatArray, unit, vec3
from m2c_kernel.protocol.errors import KernelError

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext

PARALLEL_DEG = 1.0
"""Planes within this angle count as parallel (mid-plane) or as not intersecting (axis)."""

DISPLAY_SCALE = 0.6
"""Half size of a drawn plane or axis, relative to the scan diagonal."""

DEFAULT_HALF_SIZE_MM = 50.0

STANDARD_PLANE_NORMALS: dict[StandardPlane, FloatArray] = {
    "XY": np.array([0.0, 0.0, 1.0]),
    "YZ": np.array([1.0, 0.0, 0.0]),
    "XZ": np.array([0.0, 1.0, 0.0]),
}


@dataclass(frozen=True, kw_only=True)
class OffsetPlane:
    """A plane parallel to `plane`, shifted by `distance` along its normal."""

    type: Literal["offsetPlane"] = "offsetPlane"
    plane: StandardPlane | str
    distance: float


@dataclass(frozen=True, kw_only=True)
class PlaneThroughAxis:
    """A plane containing `axis`, rotated about it by `angle_deg` (module docstring)."""

    type: Literal["planeThroughAxis"] = "planeThroughAxis"
    axis: StandardAxis | str
    angle_deg: float = 0.0


@dataclass(frozen=True, kw_only=True)
class MidPlane:
    """The plane halfway between two parallel planes."""

    type: Literal["midPlane"] = "midPlane"
    a: StandardPlane | str
    b: StandardPlane | str


@dataclass(frozen=True, kw_only=True)
class AxisFromPlanes:
    """The intersection line of two planes."""

    type: Literal["axisFromPlanes"] = "axisFromPlanes"
    a: StandardPlane | str
    b: StandardPlane | str


type ReferenceDefinition = OffsetPlane | PlaneThroughAxis | MidPlane | AxisFromPlanes


@dataclass(frozen=True, kw_only=True)
class ReferenceParams:
    definition: ReferenceDefinition


type ConstructionOf = Callable[[str], Construction]
"""Maps a feature id to its construction (`EvalContext.construction`)."""


def input_plane(name: str, construction_of: ConstructionOf) -> Plane:
    """An origin plane or the plane of a feature; `reference.notAPlane` otherwise."""
    for standard, normal in STANDARD_PLANE_NORMALS.items():
        if name == standard:
            return Plane(origin=(0.0, 0.0, 0.0), normal=vec3(normal))
    construction = construction_of(name)
    if isinstance(construction.primitive, Plane):
        return construction.primitive
    raise KernelError(ErrorCode.NOT_A_PLANE, {"feature": name})


def input_axis(name: str, construction_of: ConstructionOf) -> Axis:
    """An origin axis or the axis of a feature; `reference.notAnAxis` otherwise."""
    for standard, vector in GLOBAL_AXES.items():
        if name == standard:
            return Axis(point=(0.0, 0.0, 0.0), direction=vec3(vector))
    construction = construction_of(name)
    match construction.primitive:
        case Cylinder(origin=point, axis=direction) | Cone(apex=point, axis=direction):
            return Axis(point=point, direction=direction)
        case Torus(center=point, axis=direction):
            return Axis(point=point, direction=direction)
    if construction.axis is not None:
        return construction.axis
    raise KernelError(ErrorCode.NOT_AN_AXIS, {"feature": name})


def angle_zero_direction(axis_direction: npt.ArrayLike) -> FloatArray:
    """X (or Y for directions within 45 degrees of X), made perpendicular to the direction.

    It is the in-plane direction of `planeThroughAxis` at 0 degrees, and the edge
    direction of drawn planes.
    """
    a = unit(axis_direction)
    x_axis, y_axis = GLOBAL_AXES["X"], GLOBAL_AXES["Y"]
    reference = x_axis if abs(float(a @ x_axis)) < np.sqrt(0.5) else y_axis
    return unit(reference - (reference @ a) * a)


def _offset_plane(plane: Plane, distance: float) -> Plane:
    normal = unit(plane.normal)
    return Plane(origin=vec3(np.asarray(plane.origin) + distance * normal), normal=vec3(normal))


def _plane_through_axis(axis: Axis, angle_deg: float) -> Plane:
    a = unit(axis.direction)
    u0 = angle_zero_direction(a)
    angle = np.radians(angle_deg)
    u = np.cos(angle) * u0 + np.sin(angle) * np.cross(a, u0)
    return Plane(origin=axis.point, normal=vec3(unit(np.cross(a, u))))


def _mid_plane(a: Plane, b: Plane) -> Plane:
    na, nb = unit(a.normal), unit(b.normal)
    if angle_to_axis_deg(na, nb) > PARALLEL_DEG:
        raise KernelError(ErrorCode.NOT_PARALLEL, {"angle": angle_to_axis_deg(na, nb)})
    normal = unit(na + np.sign(float(na @ nb)) * nb)
    oa, ob = np.asarray(a.origin), np.asarray(b.origin)
    on_b = oa - ((oa - ob) @ nb) * nb
    return Plane(origin=vec3(0.5 * (oa + on_b)), normal=vec3(normal))


def _axis_from_planes(a: Plane, b: Plane, near: FloatArray) -> Axis:
    na, nb = unit(a.normal), unit(b.normal)
    if angle_to_axis_deg(na, nb) < PARALLEL_DEG:
        raise KernelError(ErrorCode.PARALLEL_PLANES, {"angle": angle_to_axis_deg(na, nb)})
    direction = unit(np.cross(na, nb))
    # The point on both planes nearest to `near`.
    system = np.array([na, nb, direction])
    rhs = np.array([na @ np.asarray(a.origin), nb @ np.asarray(b.origin), direction @ near])
    return Axis(point=vec3(np.linalg.solve(system, rhs)), direction=vec3(direction))


def _scan_extent(ctx: EvalContext) -> tuple[FloatArray, float]:
    """Centre and display half size from the scan (defaults without a scan)."""
    try:
        vertices = ctx.mesh.vertices
    except KernelError:
        return np.zeros(3), DEFAULT_HALF_SIZE_MM
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    return 0.5 * (low + high), max(DISPLAY_SCALE * float(np.linalg.norm(high - low)), 1.0)


def _plane_output(
    plane: Plane, x_dir: FloatArray, centre: FloatArray, half: float
) -> FeatureOutput:
    normal = unit(plane.normal)
    origin = np.asarray(plane.origin)
    shown = centre - ((centre - origin) @ normal) * normal
    patch = plane_patch(shown, normal, x_dir, half)
    stats = _vector_stats("point", origin) | _vector_stats("direction", normal)
    return FeatureOutput(
        construction=Construction(primitive=plane),
        display=(
            DisplaySource(
                kind="mesh", style="construction", positions=patch.positions, indices=patch.faces
            ),
            DisplaySource(kind="lines", style="constructionEdges", positions=patch.outline),
        ),
        stats=stats | _vector_stats("xDir", x_dir),
    )


def _axis_output(axis: Axis, centre: FloatArray, half: float) -> FeatureOutput:
    direction = unit(axis.direction)
    point = np.asarray(axis.point)
    shown = point + ((centre - point) @ direction) * direction
    return FeatureOutput(
        construction=Construction(axis=axis),
        display=(
            DisplaySource(
                kind="lines",
                style="constructionEdges",
                positions=axis_segment(shown, direction, half),
            ),
        ),
        stats=_vector_stats("point", point) | _vector_stats("direction", direction),
    )


def _vector_stats(name: str, vector: FloatArray) -> dict[str, float | None]:
    return {f"{name}{axis}": float(value) for axis, value in zip("XYZ", vector, strict=True)}


@feature_type("reference", params=ReferenceParams, reads=ReadSet(mesh=True))
class Reference:
    @staticmethod
    def references(params: ReferenceParams) -> Refs:
        match params.definition:
            case OffsetPlane(plane=plane):
                return Refs(features=feature_refs(plane))
            case PlaneThroughAxis(axis=axis):
                return Refs(features=feature_refs(axis))
            case MidPlane(a=a, b=b) | AxisFromPlanes(a=a, b=b):
                return Refs(features=feature_refs(a, b))

    @staticmethod
    def evaluate(ctx: EvalContext, params: ReferenceParams) -> FeatureOutput:
        centre, half = _scan_extent(ctx)
        construction_of = ctx.construction
        match params.definition:
            case OffsetPlane(plane=name, distance=distance):
                plane = _offset_plane(input_plane(name, construction_of), distance)
                return _plane_output(plane, angle_zero_direction(plane.normal), centre, half)
            case PlaneThroughAxis(axis=name, angle_deg=angle_deg):
                axis = input_axis(name, construction_of)
                plane = _plane_through_axis(axis, angle_deg)
                return _plane_output(plane, unit(axis.direction), centre, half)
            case MidPlane(a=a, b=b):
                plane = _mid_plane(input_plane(a, construction_of), input_plane(b, construction_of))
                return _plane_output(plane, angle_zero_direction(plane.normal), centre, half)
            case AxisFromPlanes(a=a, b=b):
                first, second = input_plane(a, construction_of), input_plane(b, construction_of)
                return _axis_output(_axis_from_planes(first, second, centre), centre, half)
