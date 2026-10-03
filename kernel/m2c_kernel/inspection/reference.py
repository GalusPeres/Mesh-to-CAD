"""The reference surface of the deviation analysis: a fine, watertight body tessellation.

Built once per set of bodies and tolerance: linear deflection at most tolerance / 20
(distances below the deflection are within the chord error and count as "on the
surface"), merged, subdivided so no edge is longer than 5 mm, one global B-Rep face
id per triangle, KD-trees and pseudo-normals. See `.work/research/algorithms-cad.md`
section 4.2.

BRepMesh produces long slivers on planar faces. The research used 2 mm; subdividing
a sliver keeps its aspect ratio and multiplies the triangle count, so 5 mm halves the
build time (0.4 s instead of 0.8 s for the test block) at the same accuracy: the
walkers in `distance.py` find the exact closest point on any triangulation.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import trimesh
from scipy.spatial import cKDTree

from m2c_kernel.cad.deflection import DISPLAY_LINEAR_DEFLECTION_MM
from m2c_kernel.cad.occ_compat import TopAbs_FACE, indexed_map
from m2c_kernel.cad.tessellate import tessellate
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]

ANGULAR_DEFLECTION_RAD = 0.1
MAX_EDGE_MM = 5.0
MIN_DEFLECTION_MM = 0.0005
CACHE_SIZE = 4


def reference_deflection(tolerance: float) -> float:
    """Linear deflection for the reference: tolerance / 20, never coarser than the display."""
    return float(np.clip(tolerance / 20.0, MIN_DEFLECTION_MM, DISPLAY_LINEAR_DEFLECTION_MM))


@dataclass(frozen=True)
class ReferenceSurface:
    """Plain numpy arrays (trimesh re-hashes cached properties on every access)."""

    triangles: FloatArray
    """(m, 3, 3) triangle corners."""
    faces: IntArray
    face_normals: FloatArray
    face_id: IntArray
    """Global B-Rep face index per triangle (see `body_ids` and `face_offsets`)."""
    faces_unique_edges: IntArray
    edge_normals: FloatArray
    vertex_normals: FloatArray
    vf_offsets: IntArray
    vf_faces: IntArray
    """CSR adjacency vertex -> triangles: `vf_faces[vf_offsets[v]:vf_offsets[v + 1]]`."""
    edge_vertices: IntArray
    """Vertices on B-Rep edges (shared by triangles of different B-Rep faces)."""
    centroid_tree: cKDTree
    vertex_tree: cKDTree
    edge_vertex_tree: cKDTree
    body_ids: tuple[str, ...]
    face_offsets: IntArray
    """First global face index of each body; the last entry is the total face count."""
    deflection: float
    max_edge: float
    bounds: FloatArray
    """(2, 3) minimum and maximum corner."""

    def body_face(self, global_face: int) -> tuple[str, int]:
        """Body id and B-Rep face index (`TopExp.MapShapes` order) of a global face index."""
        body = int(np.searchsorted(self.face_offsets, global_face, side="right")) - 1
        return self.body_ids[body], int(global_face - self.face_offsets[body])


def build_reference(bodies: Sequence[tuple[str, Body]], deflection: float) -> ReferenceSurface:
    """Tessellate, merge and index the bodies (body id, body) for distance queries."""
    vertex_blocks: list[FloatArray] = []
    face_blocks: list[IntArray] = []
    id_blocks: list[IntArray] = []
    offsets = [0]
    vertex_offset = 0
    for _, body in bodies:
        tess = tessellate(body.shape, deflection, ANGULAR_DEFLECTION_RAD)
        vertex_blocks.append(tess.vertices)
        face_blocks.append(tess.triangles + vertex_offset)
        id_blocks.append(tess.triangle_faces.astype(np.int64) + offsets[-1])
        vertex_offset += len(tess.vertices)
        offsets.append(offsets[-1] + indexed_map(body.shape, TopAbs_FACE).Extent())
    mesh = trimesh.Trimesh(np.vstack(vertex_blocks), np.vstack(face_blocks), process=False)
    mesh.merge_vertices()
    vertices, faces, index = trimesh.remesh.subdivide_to_size(
        mesh.vertices, mesh.faces, max_edge=MAX_EDGE_MM, max_iter=30, return_index=True
    )
    face_id = np.concatenate(id_blocks)[index]
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    mesh.merge_vertices()
    keep = mesh.nondegenerate_faces()
    if not keep.all():
        mesh.update_faces(keep)
        face_id = face_id[keep]
    return _prepare(mesh, face_id, [body_id for body_id, _ in bodies], offsets, deflection)


def _prepare(
    mesh: trimesh.Trimesh,
    face_id: IntArray,
    body_ids: list[str],
    offsets: list[int],
    deflection: float,
) -> ReferenceSurface:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    flat = faces.ravel()
    face_normals = np.asarray(mesh.face_normals, dtype=np.float64)
    faces_unique_edges = np.asarray(mesh.faces_unique_edges, dtype=np.int64)
    edge_normals = np.zeros((len(mesh.edges_unique), 3))
    np.add.at(edge_normals, faces_unique_edges.ravel(), np.repeat(face_normals, 3, axis=0))
    edge_normals /= np.maximum(np.linalg.norm(edge_normals, axis=1, keepdims=True), 1e-300)

    corner_face = np.repeat(face_id, 3)
    first_face = np.full(len(mesh.vertices), -1, dtype=np.int64)
    first_face[flat] = corner_face
    on_edge = np.zeros(len(mesh.vertices), dtype=bool)
    on_edge[flat[corner_face != first_face[flat]]] = True
    edge_vertices = np.flatnonzero(on_edge)

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    counts = np.bincount(flat, minlength=len(vertices))
    triangles = np.ascontiguousarray(vertices[faces])
    return ReferenceSurface(
        triangles=triangles,
        faces=faces,
        face_normals=face_normals,
        face_id=face_id.astype(np.int64),
        faces_unique_edges=faces_unique_edges,
        edge_normals=edge_normals,
        vertex_normals=np.asarray(mesh.vertex_normals, dtype=np.float64).copy(),
        vf_offsets=np.concatenate([[0], np.cumsum(counts)]).astype(np.int64),
        vf_faces=(np.argsort(flat, kind="stable") // 3).astype(np.int64),
        edge_vertices=edge_vertices,
        centroid_tree=cKDTree(triangles.mean(axis=1)),
        vertex_tree=cKDTree(vertices),
        edge_vertex_tree=cKDTree(vertices[edge_vertices] if len(edge_vertices) else vertices[:1]),
        body_ids=tuple(body_ids),
        face_offsets=np.asarray(offsets, dtype=np.int64),
        deflection=deflection,
        max_edge=float(mesh.edges_unique_length.max()) if len(mesh.edges_unique) else 0.0,
        bounds=np.vstack([vertices.min(axis=0), vertices.max(axis=0)]),
    )


class ReferenceCache:
    """The last few reference surfaces, by body keys and deflection.

    Body keys change whenever a body's geometry changes (they derive from result keys),
    so a cached surface is never stale.
    """

    def __init__(self, capacity: int = CACHE_SIZE) -> None:
        self._capacity = capacity
        self._items: OrderedDict[tuple[tuple[str, ...], float], ReferenceSurface] = OrderedDict()

    def get(
        self, keys: Sequence[str], bodies: Sequence[tuple[str, Body]], deflection: float
    ) -> ReferenceSurface:
        key = (tuple(keys), deflection)
        item = self._items.get(key)
        if item is None:
            item = build_reference(bodies, deflection)
            self._items[key] = item
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
        else:
            self._items.move_to_end(key)
        return item

    def clear(self) -> None:
        self._items.clear()
