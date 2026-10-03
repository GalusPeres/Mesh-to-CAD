"""Cross-sections along body edges, for measuring their rounding from the scan.

At each sample of an edge: the point, the edge's direction and, for both faces that
meet there, the direction along the face away from the edge (`fitting/corner.py`).
The direction into a face is t x n or n x t; the one whose small step stays on the
face wins (the other step leaves it across the edge).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Curve,
    BRepAdaptor_Surface,
    EdgeFaceMap,
    GeomAPI_ProjectPointOnSurf,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopExp,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    gp_Vec,
)
from m2c_kernel.cad.tags import point_distance
from m2c_kernel.fitting.corner import CornerFrame
from m2c_kernel.geometry import FloatArray, unit

SAMPLE_SPACING_MM = 0.5
MIN_SAMPLES = 12
MAX_SAMPLES = 64
STEP_MM = 0.1
"""Length of the step that tells which side of the edge a face lies on."""


def edge_frames(shape: TopoDS_Shape, edges: Sequence[TopoDS_Shape]) -> list[CornerFrame]:
    """Cross-sections along the edges, spread by length (at least one per edge)."""
    curves = [BRepAdaptor_Curve(TopoDS.Edge(edge)) for edge in edges]
    lengths = [_length(curve) for curve in curves]
    total = sum(lengths)
    count = int(np.clip(total / SAMPLE_SPACING_MM, MIN_SAMPLES, MAX_SAMPLES))
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    frames: list[CornerFrame] = []
    for edge, curve, length in zip(edges, curves, lengths, strict=True):
        index = edge_faces.FindIndex(edge)
        if index == 0:
            continue
        faces = _distinct_faces(edge_faces.FindFromIndex(index))
        if len(faces) != 2:
            continue  # a seam or a free edge: nothing to round
        share = max(1, round(count * length / max(total, 1e-12)))
        first, last = curve.FirstParameter(), curve.LastParameter()
        for k in range(share):
            parameter = first + (last - first) * (k + 0.5) / share
            frame = _frame(curve, parameter, faces)
            if frame is not None:
                frames.append(frame)
    return frames


def _length(curve: BRepAdaptor_Curve) -> float:
    first, last = curve.FirstParameter(), curve.LastParameter()
    points = np.array(
        [curve.Value(float(t)).Coord() for t in np.linspace(first, last, 33)], dtype=np.float64
    )
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def _distinct_faces(faces: object) -> list[TopoDS_Shape]:
    found: list[TopoDS_Shape] = []
    for face in faces:  # type: ignore[attr-defined]
        if not any(face.IsSame(other) for other in found):
            found.append(face)
    return found


def _frame(
    curve: BRepAdaptor_Curve, parameter: float, faces: Sequence[TopoDS_Shape]
) -> CornerFrame | None:
    point, derivative = gp_Pnt(), gp_Vec()
    curve.D1(parameter, point, derivative)
    p = np.array(point.Coord())
    tangent = unit(np.array(derivative.Coord()))
    if not np.any(tangent):
        return None
    directions: list[FloatArray] = []
    for face in faces:
        normal = _normal(TopoDS.Face(face), point)
        if normal is None:
            return None
        direction = unit(np.cross(tangent, normal))
        if not np.any(direction):
            return None
        ahead = point_distance(_tuple(p + STEP_MM * direction), face)
        behind = point_distance(_tuple(p - STEP_MM * direction), face)
        directions.append(direction if ahead <= behind else -direction)
    return CornerFrame(point=p, tangent=tangent, faces=(directions[0], directions[1]))


def _normal(face: TopoDS_Shape, point: gp_Pnt) -> FloatArray | None:
    """Unit normal of the face at its point nearest to `point`, out of the material."""
    projection = GeomAPI_ProjectPointOnSurf(point, BRep_Tool.Surface_s(face))
    if projection.NbPoints() == 0:
        return None
    u, v = projection.LowerDistanceParameters()
    surface = BRepAdaptor_Surface(face)
    at, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surface.D1(u, v, at, du, dv)
    normal = unit(np.cross(np.array(du.Coord()), np.array(dv.Coord())))
    if not np.any(normal):
        return None
    result: FloatArray = -normal if face.Orientation() == TopAbs_REVERSED else normal
    return result


def _tuple(values: FloatArray) -> tuple[float, float, float]:
    return float(values[0]), float(values[1]), float(values[2])
