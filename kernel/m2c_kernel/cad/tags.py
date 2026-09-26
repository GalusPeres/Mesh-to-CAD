"""Face tags: one name per B-Rep face that survives upstream parameter changes.

Tags are aligned with the face order of `indexed_map(shape, TopAbs_FACE)`. A
feature names the faces it creates and carries the tags of existing faces
through its operation with the builder's history (`Modified()`,
`Generated()`, `IsDeleted()`). Faces the history cannot explain (for example
after `ShapeFix_Shape`, which has no history) take the tag of the nearest
input face that contains them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepBuilderAPI_MakeVertex,
    BRepExtrema_DistShapeShape,
    BRepTools,
    ShapeMap,
    TopAbs_FACE,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    indexed_map,
)
from m2c_kernel.document.results import Body

UNTAGGED = "untagged"
_CONTAINS_TOLERANCE_MM = 1e-3


def faces_of(shape: TopoDS_Shape) -> ShapeMap:
    return indexed_map(shape, TopAbs_FACE)


def feature_tag(feature_id: str, *parts: str) -> str:
    return ":".join((feature_id, *parts))


class TagCollector:
    """Assigns tags to the faces of a result shape."""

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
        """Tag remaining faces like the nearest source face that contains their centre."""
        missing = [index for index, tag in enumerate(self._tags) if tag is None]
        if not missing:
            return
        candidates = [
            (faces_of(body.shape).FindKey(index + 1), tag)
            for body in sources
            for index, tag in enumerate(body.face_tags)
        ]
        for index in missing:
            centre = face_centre(self._faces.FindKey(index + 1))
            best: tuple[float, str] | None = None
            for face, tag in candidates:
                distance = point_distance(centre, face)
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


def face_centre(face: TopoDS_Shape) -> tuple[float, float, float]:
    """A point on the face's surface at the middle of its parameter range.

    Unlike the centre of mass it lies on the surface also for curved faces.
    """
    typed = TopoDS.Face(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(typed)
    point = BRepAdaptor_Surface(typed).Value((u_min + u_max) / 2, (v_min + v_max) / 2)
    return (point.X(), point.Y(), point.Z())


def point_distance(point: tuple[float, float, float], shape: TopoDS_Shape) -> float:
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    extrema = BRepExtrema_DistShapeShape(vertex, shape)
    if not extrema.IsDone() or extrema.NbSolution() == 0:
        return float("inf")
    return float(extrema.Value())
