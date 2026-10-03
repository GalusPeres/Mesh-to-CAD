"""Splitting a body by a plane or a freeform patch and keeping one side.

A plane gives a half-space and a boolean common (`.work/research/algorithms-cad.md`
2.6). A patch is a bounded face, so its half-space is not defined beyond its
border: the body is split with `BRepAlgoAPI_Splitter` instead and the piece on
the kept side is chosen by a point of an original face of each piece. New
faces are tagged `<tag>:split`.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

from m2c_kernel.cad.booleans import FUZZY_VALUE_MM, BooleanResult, boolean
from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Surface,
    BRepAlgoAPI_Splitter,
    BRepBuilderAPI_MakeFace,
    BRepPrimAPI_MakeHalfSpace,
    GeomAPI_ProjectPointOnSurf,
    List_TopoDS_Shape,
    Standard_Failure,
    TopAbs_REVERSED,
    TopAbs_SOLID,
    TopoDS,
    TopoDS_Shape,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Vec,
    indexed_map,
)
from m2c_kernel.cad.tags import TagCollector, faces_of, point_on_face, tag_all
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

type Side = Literal["front", "back"]


def half_space(origin: FloatArray, normal: FloatArray, tag: str) -> Body:
    """The solid on the side `normal` points to, bounded by the plane through `origin`."""
    unit_normal = unit(normal)
    plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*unit_normal))
    face = BRepBuilderAPI_MakeFace(plane).Face()
    inside = np.asarray(origin, dtype=np.float64) + unit_normal
    solid = BRepPrimAPI_MakeHalfSpace(face, gp_Pnt(*inside)).Solid()
    return tag_all(solid, tag)


def trim_by_plane(
    body: Body, origin: FloatArray, normal: FloatArray, keep: Side, tag: str
) -> BooleanResult:
    """Keep the part of `body` in front of (normal side) or behind the plane."""
    side = unit(normal) if keep == "front" else -unit(normal)
    try:
        result = boolean("intersect", body, [half_space(origin, side, f"{tag}:split")])
    except KernelError as failure:
        if failure.code == ErrorCode.NO_OVERLAP:
            raise KernelError(ErrorCode.TOOL_MISSES_BODY) from None
        raise
    before = check_solid(body.shape).volume
    if abs(check_solid(result.body.shape).volume - before) <= 1e-7 * max(before, 1.0):
        raise KernelError(ErrorCode.TOOL_MISSES_BODY)
    return result


def patch_face(surface: Any) -> TopoDS_Shape:
    """The face of a freeform construction (a face, or a surface over its parameter range)."""
    if isinstance(surface, TopoDS_Shape):
        return TopoDS.Face(surface)
    maker = BRepBuilderAPI_MakeFace(surface, 1e-6)
    if not maker.IsDone():
        raise KernelError(ErrorCode.NOT_A_PATCH)
    return maker.Face()


def trim_by_face(body: Body, face: TopoDS_Shape, keep: Side, tag: str) -> Body:
    """Split `body` with a (bounded) face and keep the piece on the `keep` side of it."""
    splitter = BRepAlgoAPI_Splitter()
    arguments = List_TopoDS_Shape()
    arguments.Append(body.shape)
    tools = List_TopoDS_Shape()
    tools.Append(face)
    splitter.SetArguments(arguments)
    splitter.SetTools(tools)
    splitter.SetFuzzyValue(FUZZY_VALUE_MM)
    splitter.SetNonDestructive(True)
    splitter.SetToFillHistory(True)
    splitter.SetRunParallel(False)
    try:
        splitter.Build()
        done = splitter.IsDone()
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": "split"}, str(failure)) from None
    if not done:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": "split"})

    solids_map = indexed_map(splitter.Shape(), TopAbs_SOLID)
    solids = [solids_map.FindKey(index) for index in range(1, solids_map.Extent() + 1)]
    if len(solids) < 2:
        raise KernelError(ErrorCode.TOOL_MISSES_BODY)
    tool_pieces = list(splitter.Modified(face))
    wanted = 1.0 if keep == "front" else -1.0
    kept = [solid for solid in solids if _side_of(solid, face, tool_pieces) == wanted]
    if not kept:
        raise KernelError(ErrorCode.TOOL_MISSES_BODY)
    if len(kept) > 1:
        raise KernelError(ErrorCode.MULTIPLE_SOLIDS, {"operation": "split", "count": len(kept)})
    collector = TagCollector(kept[0])
    collector.carry(splitter, body)
    collector.set_all(tool_pieces, f"{tag}:split")
    for index in collector.missing():
        collector.set(collector.face(index), f"{tag}:split")
    return collector.body()


def _side_of(solid: TopoDS_Shape, face: TopoDS_Shape, tool_pieces: list[TopoDS_Shape]) -> float:
    """+1 if the solid lies in front of the face (its normal side), -1 behind, 0 unknown."""
    solid_faces = faces_of(solid)
    for index in range(1, solid_faces.Extent() + 1):
        candidate = solid_faces.FindKey(index)
        if any(candidate.IsSame(piece) for piece in tool_pieces):
            continue
        distance = _signed_distance(face, np.asarray(point_on_face(candidate)))
        if abs(distance) > 1e-6:
            return float(np.sign(distance))
    return 0.0


def _signed_distance(face: TopoDS_Shape, point: FloatArray) -> float:
    """Distance of a point to the face's surface, positive on the normal side."""
    typed = TopoDS.Face(face)
    surface = BRep_Tool.Surface_s(typed)
    projection = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), surface)
    if projection.NbPoints() == 0:
        return 0.0
    u, v = projection.LowerDistanceParameters()
    foot = gp_Pnt()
    du, dv = gp_Vec(), gp_Vec()
    BRepAdaptor_Surface(typed).D1(u, v, foot, du, dv)
    normal = np.cross(np.array(du.Coord()), np.array(dv.Coord()))
    if typed.Orientation() == TopAbs_REVERSED:
        normal = -normal
    return float((point - np.array(foot.Coord())) @ unit(normal))
