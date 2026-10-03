"""Signed distances of points to the faces of a solid, to push a net past them.

Every face of a solid is a reference of its own, as QuickSurface pushes a net past
every visible face rather than out of the body as a whole: the border of a rounding
net beside the end face of a block must pass that face even after it has left the
block over the top, or net and block enclose nothing.

A face measures along its outward normal at the foot of the point on its surface,
positive outside. It speaks only near the face itself, when the foot lies within
`margin` of the face: farther away the face's surface runs where the solid has other
faces or none.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from m2c_kernel.cad.occ_compat import (
    Bnd_Box,
    BRep_Tool,
    BRepAdaptor_Surface,
    BRepBndLib,
    BRepBuilderAPI_MakeVertex,
    BRepClass_FaceClassifier,
    BRepExtrema_DistShapeShape,
    GeomAPI_ProjectPointOnSurf,
    TopAbs_FACE,
    TopAbs_OUT,
    TopAbs_REVERSED,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    gp_Pnt2d,
    gp_Vec,
    indexed_map,
)
from m2c_kernel.geometry import FloatArray, unit

type FaceMeasure = Callable[[FloatArray], tuple[float, FloatArray]]
"""Signed distance of a point to a face (positive outside) and the outward normal; an
infinite distance and a zero normal where the face does not speak."""

_FAR = (float("inf"), np.zeros(3))
_IN_FACE_MM = 1e-7
_BOX_SLACK_MM = 1e-6


def face_measures(solid: TopoDS_Shape, margin: float) -> list[FaceMeasure]:
    """One measure per face of the solid, each for points whose foot is near that face."""
    faces = indexed_map(solid, TopAbs_FACE)
    return [_face_measure(faces.FindKey(index), margin) for index in range(1, faces.Extent() + 1)]


def _face_measure(shape: TopoDS_Shape, margin: float) -> FaceMeasure:
    face = TopoDS.Face(shape)
    surface = BRep_Tool.Surface_s(face)
    adaptor = BRepAdaptor_Surface(face)
    box = Bnd_Box()
    BRepBndLib.Add_s(face, box, False)
    box.Enlarge(margin + _BOX_SLACK_MM)
    outward = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0

    def measure(point: FloatArray) -> tuple[float, FloatArray]:
        at = gp_Pnt(*np.asarray(point, dtype=np.float64))
        if box.IsOut(at):
            return _FAR
        projection = GeomAPI_ProjectPointOnSurf(at, surface)
        if projection.NbPoints() == 0:
            return _FAR
        u, v = projection.LowerDistanceParameters()
        foot, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
        adaptor.D1(u, v, foot, du, dv)
        if not _near_face(face, foot, u, v, margin):
            return _FAR
        normal = outward * unit(np.cross(np.array(du.Coord()), np.array(dv.Coord())))
        return float((np.asarray(point) - np.array(foot.Coord())) @ normal), normal

    return measure


def _near_face(face: TopoDS_Shape, foot: gp_Pnt, u: float, v: float, margin: float) -> bool:
    """Whether the foot (u, v) on the face's surface lies within `margin` of the face."""
    if BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), _IN_FACE_MM).State() != TopAbs_OUT:
        return True
    vertex = BRepBuilderAPI_MakeVertex(foot).Vertex()
    extrema = BRepExtrema_DistShapeShape(vertex, face)
    return bool(extrema.IsDone() and extrema.NbSolution() > 0 and extrema.Value() <= margin)
