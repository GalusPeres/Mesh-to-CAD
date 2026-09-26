"""Display tessellation of B-Rep shapes.

Vertices are kept per B-Rep face (not merged), which gives crisp shading at
edges and a face id per triangle for picking. Triangles of faces with reversed
orientation are flipped. Edge polylines come from `PolygonOnTriangulation`, so
they use exactly the vertices of the adjacent face. Details:
`.work/research/algorithms-cad.md` 2.9.

OCP 8 exposes no buffer access to `Poly_Triangulation`; the per-node loops
cost about 0.16 s per 100 000 triangles, which is why results are cached by
result key.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.cad.deflection import DISPLAY_ANGULAR_DEFLECTION_RAD, DISPLAY_LINEAR_DEFLECTION_MM
from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepMesh_IncrementalMesh,
    BRepTools,
    EdgeFaceMap,
    ShapeMap,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopExp,
    TopLoc_Location,
    TopoDS,
    TopoDS_Shape,
    indexed_map,
)
from m2c_kernel.geometry import FloatArray


@dataclass(frozen=True)
class Tessellation:
    """Triangles of a shape plus its edges as line segments.

    Attributes:
        vertices: (n, 3) positions, not merged across B-Rep faces.
        triangles: (m, 3) outward-wound vertex indices.
        triangle_faces: (m,) index of the B-Rep face of each triangle.
        edge_segments: (s, 2, 3) line segments of all B-Rep edges.
        segment_edges: (s,) index of the B-Rep edge of each segment.
        segment_faces: (s, 2) indices of the B-Rep faces on both sides of each segment's
            edge (the same index twice for seam and boundary edges). Fillet edge picks turn
            them into face-tag pairs (`Body.face_tags`).
    """

    vertices: FloatArray
    triangles: npt.NDArray[np.int64]
    triangle_faces: npt.NDArray[np.uint32]
    edge_segments: FloatArray
    segment_edges: npt.NDArray[np.uint32]
    segment_faces: npt.NDArray[np.uint32]


def tessellate(
    shape: TopoDS_Shape,
    linear_deflection: float = DISPLAY_LINEAR_DEFLECTION_MM,
    angular_deflection: float = DISPLAY_ANGULAR_DEFLECTION_RAD,
) -> Tessellation:
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)
    vertex_blocks: list[FloatArray] = []
    triangle_blocks: list[npt.NDArray[np.int64]] = []
    face_blocks: list[npt.NDArray[np.uint32]] = []
    offset = 0
    faces = indexed_map(shape, TopAbs_FACE)
    for face_index in range(faces.Extent()):
        face = TopoDS.Face(faces.FindKey(face_index + 1))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        transform = location.Transformation()
        nodes = np.array(
            [
                triangulation.Node(i).Transformed(transform).Coord()
                for i in range(1, triangulation.NbNodes() + 1)
            ],
            dtype=np.float64,
        )
        triangles = (
            np.array(
                [
                    triangulation.Triangle(i).Get()
                    for i in range(1, triangulation.NbTriangles() + 1)
                ],
                dtype=np.int64,
            )
            - 1
        )
        if face.Orientation() == TopAbs_REVERSED:
            triangles = triangles[:, ::-1]
        vertex_blocks.append(nodes)
        triangle_blocks.append(triangles + offset)
        face_blocks.append(np.full(len(triangles), face_index, dtype=np.uint32))
        offset += len(nodes)

    segments, segment_edges, segment_faces = _edge_segments(shape, faces)
    return Tessellation(
        vertices=np.vstack(vertex_blocks) if vertex_blocks else np.empty((0, 3)),
        triangles=np.vstack(triangle_blocks) if triangle_blocks else np.empty((0, 3), np.int64),
        triangle_faces=np.concatenate(face_blocks) if face_blocks else np.empty(0, np.uint32),
        edge_segments=segments,
        segment_edges=segment_edges,
        segment_faces=segment_faces,
    )


def _edge_segments(
    shape: TopoDS_Shape, faces: ShapeMap
) -> tuple[FloatArray, npt.NDArray[np.uint32], npt.NDArray[np.uint32]]:
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    segment_blocks: list[FloatArray] = []
    id_blocks: list[npt.NDArray[np.uint32]] = []
    face_blocks: list[npt.NDArray[np.uint32]] = []
    for edge_index in range(1, edge_faces.Extent() + 1):
        edge = TopoDS.Edge(edge_faces.FindKey(edge_index))
        adjacent = edge_faces.FindFromIndex(edge_index)
        if BRep_Tool.Degenerated_s(edge) or adjacent.Size() == 0:
            continue
        face = TopoDS.Face(adjacent.First())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location)
        if polygon is None:
            continue
        transform = location.Transformation()
        nodes = polygon.Nodes()
        polyline = np.array(
            [
                triangulation.Node(nodes.Value(i)).Transformed(transform).Coord()
                for i in range(nodes.Lower(), nodes.Upper() + 1)
            ],
            dtype=np.float64,
        )
        if len(polyline) < 2:
            continue
        side_faces = [faces.FindIndex(item) - 1 for item in adjacent]
        pair = (side_faces[0], side_faces[1] if len(side_faces) > 1 else side_faces[0])
        count = len(polyline) - 1
        segment_blocks.append(np.stack([polyline[:-1], polyline[1:]], axis=1))
        id_blocks.append(np.full(count, edge_index - 1, dtype=np.uint32))
        face_blocks.append(np.tile(np.array(pair, dtype=np.uint32), (count, 1)))
    if not segment_blocks:
        return np.empty((0, 2, 3)), np.empty(0, dtype=np.uint32), np.empty((0, 2), np.uint32)
    return (
        np.concatenate(segment_blocks),
        np.concatenate(id_blocks),
        np.concatenate(face_blocks),
    )
