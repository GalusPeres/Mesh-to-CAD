"""Signed distance of points to a solid and the outward direction there.

Positive outside the solid. Measured to the solid's shells: `BRepExtrema` treats a
solid as filled and reports 0 for points inside it. The sign comes from the normal of
the nearest face, which is cheap; only when the nearest point lies on an edge or a
vertex (where face normals disagree) the solid classifier decides.
"""

from __future__ import annotations

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Surface,
    BRepBuilderAPI_MakeVertex,
    BRepClass3d_SolidClassifier,
    BRepExtrema_DistShapeShape,
    GeomAPI_ProjectPointOnSurf,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    gp_Vec,
    indexed_map,
)
from m2c_kernel.geometry import FloatArray, unit

_ON_SURFACE_MM = 1e-7


def signed_distance(solid: TopoDS_Shape, point: FloatArray) -> tuple[float, FloatArray]:
    """Distance to the solid's boundary (negative inside) and the outward unit direction."""
    point = np.asarray(point, dtype=np.float64)
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    shells = indexed_map(solid, TopAbs_SHELL)
    candidates = [
        BRepExtrema_DistShapeShape(vertex, shells.FindKey(index))
        for index in range(1, shells.Extent() + 1)
    ]
    found = [extrema for extrema in candidates if extrema.IsDone() and extrema.NbSolution() > 0]
    if not found:
        return float("inf"), np.zeros(3)
    extrema = min(found, key=lambda candidate: candidate.Value())
    foot = np.array(extrema.PointOnShape2(1).Coord())
    distance = float(extrema.Value())
    support = extrema.SupportOnShape2(1)
    if support.ShapeType() == TopAbs_FACE:
        normal = _outward_normal(support, foot)
        if distance <= _ON_SURFACE_MM:
            return 0.0, normal
        sign = 1.0 if float((point - foot) @ normal) >= 0.0 else -1.0
        return sign * distance, normal
    inside = BRepClass3d_SolidClassifier(solid, gp_Pnt(*point), 1e-7).State() == TopAbs_IN
    if distance <= _ON_SURFACE_MM:
        return 0.0, np.zeros(3)
    away = unit(point - foot)
    return (-distance, -away) if inside else (distance, away)


def _outward_normal(face_shape: TopoDS_Shape, foot: FloatArray) -> FloatArray:
    face = TopoDS.Face(face_shape)
    projection = GeomAPI_ProjectPointOnSurf(gp_Pnt(*foot), BRep_Tool.Surface_s(face))
    u, v = projection.LowerDistanceParameters()
    at, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    BRepAdaptor_Surface(face).D1(u, v, at, du, dv)
    normal = unit(np.cross(np.array(du.Coord()), np.array(dv.Coord())))
    return -normal if face.Orientation() == TopAbs_REVERSED else normal
