"""Solid operations for the modelling features.

Every operation returns a `Body` whose faces carry tags (`cad/tags.py`); the
rebuild checks every result with `cad.check.check_solid`. Methods and
measurements: `.work/research/algorithms-cad.md` section 2.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.cad.booleans import boolean
from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Curve,
    BRepAdaptor_Surface,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Transform,
    BRepFilletAPI_MakeChamfer,
    BRepFilletAPI_MakeFillet,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeHalfSpace,
    BRepPrimAPI_MakePrism,
    BRepPrimAPI_MakeRevol,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
    GeomAbs_Plane,
    Standard_Failure,
    TopAbs_EDGE,
    TopAbs_VERTEX,
    TopExp_Explorer,
    TopoDS,
    TopoDS_Shape,
    gp_Ax1,
    gp_Ax2,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Trsf,
    gp_Vec,
)
from m2c_kernel.cad.tags import TagCollector, face_centre, faces_of, point_distance
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body, PlaneFrame
from m2c_kernel.protocol.errors import KernelError

type Vector = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Profile:
    """A planar profile face and the names of its edges (in `profile_edges` order)."""

    face: Any
    edge_names: tuple[str, ...]


def profile_edges(face: TopoDS_Shape) -> list[TopoDS_Shape]:
    """Edges of a face in explorer order (stable for equal input)."""
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    edges: list[TopoDS_Shape] = []
    while explorer.More():
        edges.append(explorer.Current())
        explorer.Next()
    return edges


def _unit(vector: Sequence[float] | Vector) -> Vector:
    array = np.asarray(vector, dtype=np.float64)
    length = float(np.linalg.norm(array))
    if length == 0.0:
        raise ValueError("zero vector")
    return array / length


def _translated(shape: TopoDS_Shape, offset: Vector) -> TopoDS_Shape:
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(*offset))
    return BRepBuilderAPI_Transform(shape, move, True).Shape()


def _fuse_all(bodies: list[Body]) -> Body:
    result = bodies[0]
    for body in bodies[1:]:
        result = boolean("add", result, [body]).body
    return result


# --- Extrude -------------------------------------------------------------------------------


def extrude(
    profiles: Sequence[Profile], direction: Vector, forward: float, backward: float, tag: str
) -> Body:
    """Extrude planar profiles `forward` along `direction` and `backward` against it.

    Faces: `<tag>:cap:start`, `<tag>:cap:end`, `<tag>:side:<edge name>`.
    """
    unit = _unit(direction)
    if forward + backward <= 0.0:
        raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "zeroLength"})
    bodies: list[Body] = []
    for profile in profiles:
        face = _translated(profile.face, -unit * backward) if backward else profile.face
        maker = BRepPrimAPI_MakePrism(face, gp_Vec(*(unit * (forward + backward))))
        maker.Build()
        if not maker.IsDone():
            raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "prism"})
        collector = TagCollector(maker.Shape())
        collector.set(maker.FirstShape(), f"{tag}:cap:start")
        collector.set(maker.LastShape(), f"{tag}:cap:end")
        for edge, name in zip(profile_edges(face), profile.edge_names, strict=False):
            collector.set_all(maker.Generated(edge), f"{tag}:side:{name}")
        bodies.append(collector.body())
    return _fuse_all(bodies)


def extrude_to_plane(
    profiles: Sequence[Profile],
    direction: Vector,
    plane_origin: Vector,
    plane_normal: Vector,
    tag: str,
) -> Body:
    """Extrude until the plane: over-extrude, then keep the half-space on the profile side."""
    unit = _unit(direction)
    normal = _unit(plane_normal)
    along = float(np.dot(unit, normal))
    if abs(along) < 1e-6:
        raise KernelError(ErrorCode.PLANE_PARALLEL)
    points = np.vstack([_vertices(profile.face) for profile in profiles])
    reach = (plane_origin - points) @ normal / along
    if reach.max() <= 1e-6:
        raise KernelError(ErrorCode.PLANE_BEHIND)
    size = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    long = extrude(profiles, unit, float(reach.max()) + size + 1.0, 0.0, tag)
    # Keep the side the profile is on: the side opposite to the extrusion direction.
    keep_normal = -normal if along > 0 else normal
    half = half_space(plane_origin, keep_normal, f"{tag}:cap:end")
    result = boolean("intersect", long, [half])
    return result.body


def _vertices(shape: TopoDS_Shape) -> Vector:
    explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
    points = []
    while explorer.More():
        points.append(BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current())).Coord())
        explorer.Next()
    return np.array(points, dtype=np.float64).reshape(-1, 3)


# --- Revolve -------------------------------------------------------------------------------


def revolve(
    profiles: Sequence[Profile],
    frame: PlaneFrame,
    axis_point: Vector,
    axis_direction: Vector,
    angle_deg: float,
    tag: str,
) -> Body:
    """Revolve planar profiles about an axis in their plane.

    Faces: `<tag>:rev:<edge name>`, and `<tag>:cap:start` / `<tag>:cap:end` below 360 degrees.
    """
    point, direction = _axis_in_plane(frame, axis_point, axis_direction)
    for profile in profiles:
        _check_axis_side(profile.face, frame, point, direction)
    axis = gp_Ax1(gp_Pnt(*point), gp_Dir(*direction))
    full = angle_deg >= 360.0 - 1e-9
    bodies: list[Body] = []
    for profile in profiles:
        maker = (
            BRepPrimAPI_MakeRevol(profile.face, axis)
            if full
            else BRepPrimAPI_MakeRevol(profile.face, axis, math.radians(angle_deg))
        )
        maker.Build()
        if not maker.IsDone():
            raise KernelError(ErrorCode.INVALID_RESULT, {"reason": "revolve"})
        collector = TagCollector(maker.Shape())
        if not full:
            collector.set(maker.FirstShape(), f"{tag}:cap:start")
            collector.set(maker.LastShape(), f"{tag}:cap:end")
        edges = list(zip(profile_edges(profile.face), profile.edge_names, strict=False))
        for edge, name in edges:
            collector.set_all(maker.Generated(edge), f"{tag}:rev:{name}")
        _tag_swept_faces(collector, edges, frame, point, direction, tag)
        bodies.append(collector.body())
    return _fuse_all(bodies)


def _tag_swept_faces(
    collector: TagCollector,
    edges: list[tuple[TopoDS_Shape, str]],
    frame: PlaneFrame,
    point: Vector,
    direction: Vector,
    tag: str,
) -> None:
    """Tag faces the revolve history misses (OCCT returns no `Generated` faces for edges
    perpendicular to the axis of a full revolve): rotate a point of the face back into the
    profile plane and take the nearest profile edge."""
    in_plane = np.cross(frame.normal, direction)
    samples = np.vstack([_edge_samples(edge) for edge, _name in edges])
    if float(np.mean((samples - point) @ in_plane)) < 0:
        in_plane = -in_plane
    for index in collector.missing():
        face_point = np.asarray(face_centre(collector.face(index))) - point
        height = float(face_point @ direction)
        radius = float(np.linalg.norm(face_point - height * direction))
        back = tuple(point + height * direction + radius * in_plane)
        name = min(edges, key=lambda item: point_distance(back, item[0]))[1]
        collector.set(collector.face(index), f"{tag}:rev:{name}")


def _axis_in_plane(
    frame: PlaneFrame, point: Vector, direction: Vector
) -> tuple[Vector, Vector]:
    normal = _unit(frame.normal)
    unit = _unit(direction)
    distance = float(np.dot(np.asarray(point) - frame.origin, normal))
    if abs(float(np.dot(unit, normal))) > 1e-6 or abs(distance) > 1e-4:
        raise KernelError(ErrorCode.AXIS_NOT_IN_PLANE)
    return np.asarray(point, dtype=np.float64) - distance * normal, unit


def _check_axis_side(face: TopoDS_Shape, frame: PlaneFrame, point: Vector, direction: Vector) -> None:
    """The profile must lie on one side of the axis (touching it is allowed)."""
    side_normal = np.cross(direction, frame.normal)
    samples = np.vstack([_edge_samples(edge) for edge in profile_edges(face)])
    sides = (samples - point) @ side_normal
    tolerance = 1e-6
    if sides.max() > tolerance and sides.min() < -tolerance:
        raise KernelError(ErrorCode.AXIS_CROSSES_PROFILE)


def _edge_samples(edge: TopoDS_Shape, count: int = 17) -> Vector:
    curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
    parameters = np.linspace(curve.FirstParameter(), curve.LastParameter(), count)
    return np.array([curve.Value(float(t)).Coord() for t in parameters], dtype=np.float64)


# --- Primitive bodies ----------------------------------------------------------------------


def _perpendicular(axis: Vector, hint: Vector | None) -> Vector:
    candidates = [] if hint is None else [np.asarray(hint, dtype=np.float64)]
    candidates += [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])]
    for candidate in candidates:
        projected = candidate - np.dot(candidate, axis) * axis
        if np.linalg.norm(projected) > 1e-6:
            return _unit(projected)
    raise ValueError("no perpendicular direction")


def _axis_frame(origin: Vector, axis: Vector, x_hint: Vector | None) -> gp_Ax2:
    return gp_Ax2(gp_Pnt(*origin), gp_Dir(*axis), gp_Dir(*_perpendicular(axis, x_hint)))


def _tag_caps(shape: TopoDS_Shape, base: Vector, axis: Vector, tag: str, lateral: str) -> Body:
    """Planar faces become `cap:start` / `cap:end` by their side along the axis."""
    collector = TagCollector(shape)
    faces = faces_of(shape)
    for index in range(1, faces.Extent() + 1):
        face = faces.FindKey(index)
        if BRepAdaptor_Surface(TopoDS.Face(face)).GetType() == GeomAbs_Plane:
            height = float(np.dot(np.asarray(face_centre(face)) - base, axis))
            collector.set(face, f"{tag}:cap:{'end' if height > 1e-9 else 'start'}")
        else:
            collector.set(face, f"{tag}:{lateral}")
    return collector.body()


def cylinder(
    base: Vector, axis: Vector, radius: float, length: float, tag: str, x_hint: Vector | None = None
) -> Body:
    unit = _unit(axis)
    shape = BRepPrimAPI_MakeCylinder(_axis_frame(base, unit, x_hint), radius, length).Shape()
    return _tag_caps(shape, base, unit, tag, "lateral")


def cone(
    base: Vector,
    axis: Vector,
    radius_start: float,
    radius_end: float,
    length: float,
    tag: str,
    x_hint: Vector | None = None,
) -> Body:
    unit = _unit(axis)
    frame = _axis_frame(base, unit, x_hint)
    shape = BRepPrimAPI_MakeCone(frame, radius_start, radius_end, length).Shape()
    return _tag_caps(shape, base, unit, tag, "lateral")


def sphere(center: Vector, radius: float, tag: str) -> Body:
    shape = BRepPrimAPI_MakeSphere(gp_Pnt(*center), radius).Shape()
    return Body(shape, tuple(f"{tag}:surface" for _ in range(faces_of(shape).Extent())))


def torus(
    center: Vector, axis: Vector, major: float, minor: float, tag: str, x_hint: Vector | None = None
) -> Body:
    shape = BRepPrimAPI_MakeTorus(_axis_frame(center, _unit(axis), x_hint), major, minor).Shape()
    return Body(shape, tuple(f"{tag}:surface" for _ in range(faces_of(shape).Extent())))


# --- Trim ----------------------------------------------------------------------------------


def half_space(origin: Vector, normal: Vector, tag: str) -> Body:
    """The solid on the side `normal` points to, bounded by the plane through `origin`."""
    unit = _unit(normal)
    plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*unit))
    face = BRepBuilderAPI_MakeFace(plane).Face()
    return half_space_of_face(face, np.asarray(origin, dtype=np.float64) + unit, tag)


def half_space_of_face(face: TopoDS_Shape, inside: Vector, tag: str) -> Body:
    solid = BRepPrimAPI_MakeHalfSpace(TopoDS.Face(face), gp_Pnt(*inside)).Solid()
    return Body(solid, tuple(tag for _ in range(faces_of(solid).Extent())))


def trim_by_plane(
    body: Body, origin: Vector, normal: Vector, keep: Literal["front", "back"], tag: str
) -> tuple[Body, tuple[Any, ...]]:
    """Keep the part of `body` in front of (normal side) or behind the plane."""
    unit = _unit(normal)
    side = unit if keep == "front" else -unit
    result = boolean("intersect", body, [half_space(origin, side, f"{tag}:cut")])
    return result.body, result.issues


# --- Fillet and chamfer --------------------------------------------------------------------


def fillet_edges(
    body: Body, edges: list[TopoDS_Shape], size: float, chamfer: bool, tag: str
) -> Body:
    """Constant-radius fillet or symmetric chamfer; new faces are `<tag>:fillet:<n>`."""
    maker: Any = BRepFilletAPI_MakeChamfer(body.shape) if chamfer else BRepFilletAPI_MakeFillet(
        body.shape
    )
    for edge in edges:
        maker.Add(size, TopoDS.Edge(edge))
    try:
        maker.Build()
        done = maker.IsDone()
        shape = maker.Shape() if done else None
    except Standard_Failure:
        done, shape = False, None
    if not done or shape is None:
        faulty = 0 if chamfer else int(maker.NbFaultyContours())
        raise KernelError(ErrorCode.FILLET_FAILED, {"contours": faulty, "size": size})
    collector = TagCollector(shape)
    collector.carry(maker, body)
    for index, edge in enumerate(edges):
        collector.set_all(maker.Generated(edge), f"{tag}:fillet:{index}")
    collector.fill_by_proximity([body])
    return collector.body()
