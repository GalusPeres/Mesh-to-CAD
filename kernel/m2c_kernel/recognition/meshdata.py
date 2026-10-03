"""What every plane's relief search needs of the mesh: adjacency and robust normals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]

NORMAL_SMOOTHING_MM = 0.4
"""Vertex normals are averaged over neighbours about this far away."""
MAX_NORMAL_RINGS = 6


@dataclass(frozen=True)
class MeshData:
    """What every plane's search needs of the mesh, computed once."""

    vertices: FloatArray
    faces: IntArray
    graph: sp.csr_matrix
    """Vertex adjacency."""
    normals: FloatArray
    """Smoothed unit vertex normals (`vertex_normals`)."""
    face_normals: FloatArray
    """(F, 2, 3) unit triangle normals: the triangle's own, and the mean of its smoothed
    corner normals (`face_normals`)."""


def mesh_data(vertices: FloatArray, faces: IntArray) -> MeshData:
    n = len(vertices)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    graph = sp.csr_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    graph = (graph + graph.T).tocsr()
    graph.data[:] = 1.0
    normals = vertex_normals(vertices, faces, graph)
    return MeshData(vertices, faces, graph, normals, face_normals(vertices, faces, normals))


def _rings(corners: FloatArray) -> int:
    """Neighbour rings that span about `NORMAL_SMOOTHING_MM` on this mesh."""
    edge = float(np.mean(np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1)))
    return int(np.clip(round(NORMAL_SMOOTHING_MM / max(edge, 1e-9)), 0, MAX_NORMAL_RINGS))


def face_normals(vertices: FloatArray, faces: IntArray, normals: FloatArray) -> FloatArray:
    """Each triangle's own unit normal and the mean of its smoothed corner normals.

    The own normal is exact on CAD exports but follows the noise on scans with thin
    triangles; the corner mean is robust on scans but blends both sides at the sharp
    edges of CAD exports.
    """
    corners = vertices[faces]
    own = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    result = np.stack([own, normals[faces].sum(axis=1)], axis=1)
    unit: FloatArray = result / np.maximum(np.linalg.norm(result, axis=2, keepdims=True), 1e-300)
    return unit


def vertex_normals(vertices: FloatArray, faces: IntArray, graph: sp.csr_matrix) -> FloatArray:
    """Area-weighted vertex normals, averaged over neighbours `NORMAL_SMOOTHING_MM` away.

    On dense scans single-vertex normals follow the noise (0.02 mm noise on 0.1 mm
    triangles tilts them by tens of degrees); the walls and floors only need the
    direction of the surface around the point. The number of neighbour rings
    follows the edge length, so coarse meshes are not smoothed across whole faces.
    """
    corners = vertices[faces]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    result = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(result, faces[:, corner], normal)
    for _ in range(_rings(corners)):
        result = result + graph @ result
        result /= np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-300)
    length = np.linalg.norm(result, axis=1, keepdims=True)
    normals: FloatArray = result / np.maximum(length, 1e-300)
    return normals
