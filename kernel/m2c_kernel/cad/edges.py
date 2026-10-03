"""Resolution of edge references (fillets, chamfers) by face-tag pairs.

An edge reference names the tags of the two faces on both sides of the edge and
a point on it. Candidates are the edges between faces carrying these tags; when
a boolean split a tagged face there can be several, and the one closest to the
point wins (ARCHITECTURE.md 4.6).
"""

from __future__ import annotations

from collections.abc import Sequence

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    EdgeFaceMap,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopExp,
    TopoDS,
    TopoDS_Shape,
)
from m2c_kernel.cad.tags import faces_of, point_distance
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.errors import KernelError

type Point = tuple[float, float, float]


def resolve_edge(body: Body, faces: tuple[str, str], point: Point, index: int) -> TopoDS_Shape:
    """The edge of `body` between faces tagged `faces`, closest to `point`."""
    candidates = edges_between(body, faces)
    if not candidates:
        raise KernelError(ErrorCode.EDGE_NOT_FOUND, {"index": index})
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda edge: point_distance(point, edge))


def resolve_edges(body: Body, refs: Sequence[tuple[tuple[str, str], Point]]) -> list[TopoDS_Shape]:
    return [resolve_edge(body, faces, point, index) for index, (faces, point) in enumerate(refs)]


def edges_between(body: Body, faces: tuple[str, str]) -> list[TopoDS_Shape]:
    wanted = sorted(faces)
    face_map = faces_of(body.shape)
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(body.shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    found: list[TopoDS_Shape] = []
    for edge_index in range(1, edge_faces.Extent() + 1):
        edge = TopoDS.Edge(edge_faces.FindKey(edge_index))
        if BRep_Tool.Degenerated_s(edge):
            continue
        indices = {face_map.FindIndex(face) for face in edge_faces.FindFromIndex(edge_index)}
        tags = sorted(body.face_tags[i - 1] for i in indices if 0 < i <= len(body.face_tags))
        if len(indices) == 1 and len(tags) == 1:
            tags = tags * 2  # seam edge: the same face on both sides
        if tags == wanted:
            found.append(edge)
    return found
