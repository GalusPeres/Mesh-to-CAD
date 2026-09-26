"""Solids built from profiles and fitted primitives.

Every function returns a `Body` whose faces carry tags (`cad/tags.py`):

| Solid     | Face tags                                                         |
| --------- | ----------------------------------------------------------------- |
| extrusion | `<tag>:cap:start`, `<tag>:cap:end`, `<tag>:side:<edge name>`      |
| revolve   | `<tag>:rev:<edge name>`; `<tag>:cap:start/end` below 360 degrees  |
| primitive | `<tag>:surface`; cylinders and cones also `<tag>:cap:start/end`   |

The rebuild checks every result with `cad.check.check_solid`. Methods and
measured volumes: `.work/research/algorithms-cad.md` 2.1-2.3.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from m2c_kernel.cad.booleans import boolean
from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepBuilderAPI_Transform,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
    BRepPrimAPI_MakeRevol,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
    GeomAbs_Plane,
    Standard_Failure,
    TopoDS,
    TopoDS_Shape,
    gp_Ax1,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
    gp_Trsf,
    gp_Vec,
)
from m2c_kernel.cad.profiles import (
    Profile,
    edge_samples,
    profile_edges,
    profile_samples,
)
from m2c_kernel.cad.tags import TagCollector, faces_of, point_distance, point_on_face, tag_all
from m2c_kernel.cad.trim import half_space
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body, PlaneFrame
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

_LENGTH_EPSILON_MM = 1e-6


def _translated(shape: TopoDS_Shape, offset: FloatArray) -> TopoDS_Shape:
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(*offset))
    return BRepBuilderAPI_Transform(shape, move, True).Shape()


def _fuse_all(bodies: list[Body]) -> Body:
    """Several profiles give one body; separate islands are an error (one solid per body)."""
    result = bodies[0]
    for body in bodies[1:]:
        result = boolean("add", result, [body]).body
    return result


# --- Extrude -------------------------------------------------------------------------------


def extrude(
    profiles: Sequence[Profile], direction: FloatArray, forward: float, backward: float, tag: str
) -> Body:
    """Extrude planar profiles `forward` along `direction` and `backward` against it."""
    unit_direction = unit(direction)
    length = forward + backward
    if length <= _LENGTH_EPSILON_MM:
        raise KernelError(ErrorCode.ZERO_LENGTH)
    bodies: list[Body] = []
    for profile in profiles:
        face = profile.face
        if abs(backward) > 0.0:
            face = _translated(face, -unit_direction * backward)
        maker = BRepPrimAPI_MakePrism(face, gp_Vec(*(unit_direction * length)))
        maker.Build()
        if not maker.IsDone():
            raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "prism"})
        collector = TagCollector(maker.Shape())
        collector.set(maker.FirstShape(), f"{tag}:cap:start")
        collector.set(maker.LastShape(), f"{tag}:cap:end")
        for edge, name in zip(profile_edges(face), profile.edge_names, strict=True):
            collector.set_all(maker.Generated(edge), f"{tag}:side:{name}")
        bodies.append(collector.body())
    return _fuse_all(bodies)


def extrude_to_plane(
    profiles: Sequence[Profile],
    direction: FloatArray,
    plane_origin: FloatArray,
    plane_normal: FloatArray,
    tag: str,
) -> Body:
    """Extrude until the plane: over-extrude, then keep the half-space on the profile side.

    The face on the plane is tagged `<tag>:cap:end`, like the end of a distance extrusion.
    """
    unit_direction = unit(direction)
    normal = unit(plane_normal)
    along = float(unit_direction @ normal)
    if abs(along) < 1e-6:
        raise KernelError(ErrorCode.PLANE_PARALLEL)
    points = profile_samples(profiles)
    reach = (np.asarray(plane_origin) - points) @ normal / along
    if reach.max() <= _LENGTH_EPSILON_MM:
        raise KernelError(ErrorCode.PLANE_BEHIND)
    size = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    overshoot = extrude(profiles, unit_direction, float(reach.max()) + size + 1.0, 0.0, tag)
    # The kept side is the one the extrusion comes from.
    keep_normal = -normal if along > 0 else normal
    limit = half_space(np.asarray(plane_origin), keep_normal, f"{tag}:cap:end")
    return boolean("intersect", overshoot, [limit]).body


# --- Revolve -------------------------------------------------------------------------------


def revolve(
    profiles: Sequence[Profile],
    frame: PlaneFrame,
    axis_point: FloatArray,
    axis_direction: FloatArray,
    angle_deg: float,
    tag: str,
) -> Body:
    """Revolve planar profiles about an axis in their plane, counter-clockwise about it."""
    if angle_deg <= 1e-6:
        raise KernelError(ErrorCode.ZERO_LENGTH)
    point, direction = _axis_in_plane(frame, axis_point, axis_direction)
    for profile in profiles:
        _check_axis_side(profile.face, frame, point, direction)
    axis = gp_Ax1(gp_Pnt(*point), gp_Dir(*direction))
    full = angle_deg >= 360.0 - 1e-9
    bodies: list[Body] = []
    for profile in profiles:
        try:
            maker = (
                BRepPrimAPI_MakeRevol(profile.face, axis)
                if full
                else BRepPrimAPI_MakeRevol(profile.face, axis, math.radians(angle_deg))
            )
            maker.Build()
        except Standard_Failure as failure:
            raise KernelError(
                ErrorCode.INVALID_RESULT, {"reason": "revolve"}, str(failure)
            ) from None
        if not maker.IsDone():
            raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "revolve"})
        collector = TagCollector(maker.Shape())
        if not full:
            collector.set(maker.FirstShape(), f"{tag}:cap:start")
            collector.set(maker.LastShape(), f"{tag}:cap:end")
        edges = list(zip(profile_edges(profile.face), profile.edge_names, strict=True))
        for edge, name in edges:
            collector.set_all(maker.Generated(edge), f"{tag}:rev:{name}")
        _tag_swept_faces(collector, edges, frame, point, direction, tag)
        bodies.append(collector.body())
    return _fuse_all(bodies)


def _tag_swept_faces(
    collector: TagCollector,
    edges: list[tuple[TopoDS_Shape, str]],
    frame: PlaneFrame,
    point: FloatArray,
    direction: FloatArray,
    tag: str,
) -> None:
    """Tag faces the revolve history misses.

    OCCT returns no `Generated` faces for some edges of a full revolution (edges
    perpendicular to the axis): rotate a point of such a face back into the
    profile's half-plane and take the nearest profile edge.
    """
    missing = collector.missing()
    if not missing:
        return
    in_plane = np.cross(frame.normal, direction)
    samples = np.vstack([edge_samples(edge) for edge, _name in edges])
    if float(np.mean((samples - point) @ in_plane)) < 0:
        in_plane = -in_plane
    for index in missing:
        face = collector.face(index)
        relative = np.asarray(point_on_face(face)) - point
        height = float(relative @ direction)
        radius = float(np.linalg.norm(relative - height * direction))
        back = point + height * direction + radius * in_plane
        location = (float(back[0]), float(back[1]), float(back[2]))
        name = min(edges, key=lambda item: point_distance(location, item[0]))[1]
        collector.set(face, f"{tag}:rev:{name}")


AXIS_PLANE_ANGLE_RAD = math.radians(0.1)
AXIS_PLANE_DISTANCE_MM = 0.05


def _axis_in_plane(
    frame: PlaneFrame, point: FloatArray, direction: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """The axis projected into the sketch plane.

    A fitted axis lies in a sketch plane built through it only up to rounding, so
    small deviations are projected away; larger ones are an error.
    """
    normal = unit(frame.normal)
    unit_direction = unit(direction)
    distance = float((np.asarray(point) - frame.origin) @ normal)
    tilt = abs(float(unit_direction @ normal))
    if tilt > math.sin(AXIS_PLANE_ANGLE_RAD) or abs(distance) > AXIS_PLANE_DISTANCE_MM:
        raise KernelError(
            ErrorCode.AXIS_NOT_IN_PLANE,
            {"distance": abs(distance), "angleDeg": math.degrees(math.asin(min(tilt, 1.0)))},
        )
    in_plane = unit(unit_direction - float(unit_direction @ normal) * normal)
    return np.asarray(point, dtype=np.float64) - distance * normal, in_plane


def _check_axis_side(
    face: TopoDS_Shape, frame: PlaneFrame, point: FloatArray, direction: FloatArray
) -> None:
    """The profile must lie on one side of the axis (touching it is allowed)."""
    side_normal = np.cross(direction, frame.normal)
    samples = np.vstack([edge_samples(edge) for edge in profile_edges(face)])
    sides = (samples - point) @ side_normal
    tolerance = 1e-6
    if sides.max() > tolerance and sides.min() < -tolerance:
        raise KernelError(ErrorCode.AXIS_CROSSES_PROFILE)


# --- Primitive bodies ----------------------------------------------------------------------


def _perpendicular(axis: FloatArray, hint: FloatArray | None) -> FloatArray:
    candidates = [] if hint is None else [np.asarray(hint, dtype=np.float64)]
    candidates += [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])]
    for candidate in candidates:
        projected = candidate - float(candidate @ axis) * axis
        if np.linalg.norm(projected) > 1e-6:
            return unit(projected)
    raise ValueError("no direction perpendicular to the axis")


def _axis_frame(origin: FloatArray, axis: FloatArray, seam: FloatArray | None) -> gp_Ax2:
    """Frame with Z along the axis; X points to where OCCT puts the seam of the surface."""
    return gp_Ax2(gp_Pnt(*origin), gp_Dir(*axis), gp_Dir(*_perpendicular(axis, seam)))


def _tag_caps(shape: TopoDS_Shape, base: FloatArray, axis: FloatArray, tag: str) -> Body:
    """Planar faces become `cap:start` / `cap:end` by their side along the axis."""
    collector = TagCollector(shape)
    faces = faces_of(shape)
    for index in range(1, faces.Extent() + 1):
        face = faces.FindKey(index)
        if BRepAdaptor_Surface(TopoDS.Face(face)).GetType() == GeomAbs_Plane:
            height = float((np.asarray(point_on_face(face)) - base) @ axis)
            collector.set(face, f"{tag}:cap:{'end' if height > 1e-9 else 'start'}")
        else:
            collector.set(face, f"{tag}:surface")
    return collector.body()


def cylinder(
    base: FloatArray,
    axis: FloatArray,
    radius: float,
    length: float,
    tag: str,
    seam: FloatArray | None = None,
) -> Body:
    if radius <= 0.0 or length <= _LENGTH_EPSILON_MM:
        raise KernelError(ErrorCode.ZERO_LENGTH)
    unit_axis = unit(axis)
    frame = _axis_frame(base, unit_axis, seam)
    shape = BRepPrimAPI_MakeCylinder(frame, radius, length).Shape()
    return _tag_caps(shape, base, unit_axis, tag)


def cone(
    base: FloatArray,
    axis: FloatArray,
    radius_start: float,
    radius_end: float,
    length: float,
    tag: str,
    seam: FloatArray | None = None,
) -> Body:
    """Frustum from `base` along `axis`; one of the radii may be zero (a full cone)."""
    if length <= _LENGTH_EPSILON_MM or max(radius_start, radius_end) <= 0.0:
        raise KernelError(ErrorCode.ZERO_LENGTH)
    unit_axis = unit(axis)
    frame = _axis_frame(base, unit_axis, seam)
    shape = BRepPrimAPI_MakeCone(frame, radius_start, radius_end, length).Shape()
    return _tag_caps(shape, base, unit_axis, tag)


def sphere(center: FloatArray, radius: float, tag: str) -> Body:
    if radius <= 0.0:
        raise KernelError(ErrorCode.ZERO_LENGTH)
    return tag_all(BRepPrimAPI_MakeSphere(gp_Pnt(*center), radius).Shape(), f"{tag}:surface")


def torus(
    center: FloatArray,
    axis: FloatArray,
    major: float,
    minor: float,
    tag: str,
    seam: FloatArray | None = None,
) -> Body:
    if minor <= 0.0 or major <= minor:
        raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "torusRadii"})
    frame = _axis_frame(center, unit(axis), seam)
    return tag_all(BRepPrimAPI_MakeTorus(frame, major, minor).Shape(), f"{tag}:surface")
