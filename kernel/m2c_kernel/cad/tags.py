"""Face tags: one name per B-Rep face that survives upstream parameter changes.

Tags are aligned with the face order of `indexed_map(shape, TopAbs_FACE)`. A
feature names the faces it creates (`<feature>:<role>...`, see
`document.results`) and carries the tags of existing faces through its
operation with the builder's history (`Modified()`, `IsDeleted()`). Faces the
history cannot explain (after `ShapeFix_Shape`, which keeps no history) take the
tag of the input face that contains a point of them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepBuilderAPI_MakeVertex,
    BRepClass_FaceClassifier,
    BRepExtrema_DistShapeShape,
    BRepTools,
    ShapeMap,
    TopAbs_FACE,
    TopAbs_IN,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    gp_Pnt2d,
    indexed_map,
)
from m2c_kernel.document.results import Body

UNTAGGED = "untagged"
_CONTAINS_TOLERANCE_MM = 1e-3

type Point = tuple[float, float, float]


def faces_of(shape: TopoDS_Shape) -> ShapeMap:
    return indexed_map(shape, TopAbs_FACE)


class TagCollector:
    """Assigns tags to the faces of a result shape; the first tag a face gets wins."""

    def __init__(self, result: TopoDS_Shape) -> None:
        self.result = result
        self._faces = faces_of(result)
        self._tags: list[str | None] = [None] * self._faces.Extent()

    def set(self, face: TopoDS_Shape, tag: str) -> None:
        """Tag `face` if it is a face of the result (orientation is ignored)."""
        index = self._faces.FindIndex(face)
        if index > 0 and self._tags[index - 1] is None:
            self._tags[index - 1] = tag

    def set_all(self, faces: Iterable[TopoDS_Shape], tag: str) -> None:
        for face in faces:
            self.set(face, tag)

    def carry(self, history: Any, source: Body) -> None:
        """Carry the tags of `source` through a builder's history."""
        source_faces = faces_of(source.shape)
        for index, tag in enumerate(source.face_tags):
            face = source_faces.FindKey(index + 1)
            if history.IsDeleted(face):
                continue
            modified = list(history.Modified(face))
            if modified:
                self.set_all(modified, tag)
            else:
                self.set(face, tag)

    def fill_by_proximity(self, sources: Sequence[Body]) -> None:
        """Tag remaining faces like the source face that contains a point of them."""
        missing = self.missing()
        if not missing:
            return
        candidates = [
            (faces_of(body.shape).FindKey(index + 1), tag)
            for body in sources
            for index, tag in enumerate(body.face_tags)
        ]
        for index in missing:
            point = point_on_face(self.face(index))
            best: tuple[float, str] | None = None
            for face, tag in candidates:
                distance = point_distance(point, face)
                if distance <= _CONTAINS_TOLERANCE_MM and (best is None or distance < best[0]):
                    best = (distance, tag)
            if best is not None:
                self._tags[index] = best[1]

    def missing(self) -> list[int]:
        """Indices (0-based) of faces without a tag so far."""
        return [index for index, tag in enumerate(self._tags) if tag is None]

    def face(self, index: int) -> TopoDS_Shape:
        return self._faces.FindKey(index + 1)

    def tags(self) -> tuple[str, ...]:
        return tuple(tag if tag is not None else UNTAGGED for tag in self._tags)

    def body(self) -> Body:
        return Body(self.result, self.tags())


def tag_all(shape: TopoDS_Shape, tag: str) -> Body:
    return Body(shape, tuple(tag for _ in range(faces_of(shape).Extent())))


def point_on_face(face: TopoDS_Shape) -> Point:
    """A point inside the face (not on its boundary, not in a hole).

    Tries the middle of the parameter range first, then a grid of parameters,
    and classifies each candidate against the face's boundary.
    """
    typed = TopoDS.Face(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(typed)
    surface = BRepAdaptor_Surface(typed)
    candidates = [(0.5, 0.5)] + [
        (float(a), float(b)) for a in np.linspace(0.1, 0.9, 5) for b in np.linspace(0.1, 0.9, 5)
    ]
    for a, b in candidates:
        u = u_min + a * (u_max - u_min)
        v = v_min + b * (v_max - v_min)
        if BRepClass_FaceClassifier(typed, gp_Pnt2d(u, v), 1e-7).State() == TopAbs_IN:
            point = surface.Value(u, v)
            return (point.X(), point.Y(), point.Z())
    point = surface.Value((u_min + u_max) / 2, (v_min + v_max) / 2)
    return (point.X(), point.Y(), point.Z())


def point_distance(point: Point, shape: TopoDS_Shape) -> float:
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    extrema = BRepExtrema_DistShapeShape(vertex, shape)
    if not extrema.IsDone() or extrema.NbSolution() == 0:
        return float("inf")
    return float(extrema.Value())
