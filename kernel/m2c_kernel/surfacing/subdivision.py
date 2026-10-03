"""Catmull-Clark subdivision as sparse linear maps.

Every position the surfacing pipeline needs is a fixed linear combination of the
control-cage vertices: a subdivision step maps the vertices of a mesh to those of
the refined mesh, and the limit position of a vertex is a weighted average of its
one-ring. The fit therefore works with sparse matrices and never re-subdivides
geometry.

Vertex layout after a step: vertex points, then edge points, then face points.
Boundaries follow the crease rules (the boundary becomes a cubic B-spline curve);
boundary vertices with a single face, and vertices where two boundary loops touch,
are kept as corners.

Patches: after the first step every face is a quad, and each quad of the control
cage is refined as a regular grid. `PatchGrids` keeps, for every cage quad, the
vertex indices of that grid at the current level, so limit positions come out as
one (m + 1) x (m + 1) sample grid per patch. Grid axis 1 runs from quad corner 0
to corner 1 (u), axis 2 from corner 0 to corner 3 (v).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


class TopologyError(ValueError):
    """The polygon mesh is not an oriented 2-manifold (boundaries are allowed)."""


@dataclass(frozen=True)
class EdgeTopology:
    """Edges of a polygon mesh whose faces all have the same number of corners.

    Attributes:
        edges: (e, 2) vertex pairs, smaller index first, ordered by `keys`.
        keys: (e,) sorted edge keys `low * n_vertices + high`.
        face_edges: (f, k) edge of each face side; side i runs from corner i to i + 1.
        edge_faces: (e, 2) faces on both sides of each edge; -1 marks the open side of a
            boundary edge.
        n_vertices: Number of vertices the faces index into.
    """

    edges: IntArray
    keys: IntArray
    face_edges: IntArray
    edge_faces: IntArray
    n_vertices: int

    @property
    def boundary(self) -> BoolArray:
        return self.edge_faces[:, 1] < 0

    def edge_ids(self, a: IntArray, b: IntArray) -> IntArray:
        """Edge ids of the vertex pairs `(a, b)`, which must be edges of the mesh."""
        query = np.minimum(a, b) * self.n_vertices + np.maximum(a, b)
        ids = np.searchsorted(self.keys, query)
        found = self.keys[np.minimum(ids, len(self.keys) - 1)] == query
        if not np.all(found):
            raise TopologyError("vertex pair is not an edge")
        return ids.astype(np.int64)


def edge_topology(faces: IntArray, n_vertices: int) -> EdgeTopology:
    """Edges of `faces` with their adjacent faces; checks manifoldness and orientation."""
    n_faces, corners = faces.shape
    start = faces.ravel()
    end = np.roll(faces, -1, axis=1).ravel()
    if np.any(start == end):
        raise TopologyError("a face has a degenerate side")
    keys = np.minimum(start, end) * n_vertices + np.maximum(start, end)
    unique, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    if counts.max(initial=0) > 2:
        raise TopologyError("an edge has more than two faces")
    order = np.argsort(inverse, kind="stable")
    first = np.concatenate([[0], np.cumsum(counts)[:-1]])
    half_edge_face = np.repeat(np.arange(n_faces, dtype=np.int64), corners)
    edge_faces = np.full((len(unique), 2), -1, dtype=np.int64)
    edge_faces[:, 0] = half_edge_face[order[first]]
    shared = counts == 2
    edge_faces[shared, 1] = half_edge_face[order[first[shared] + 1]]
    # The two sides of an interior edge must traverse it in opposite directions.
    forward = (start < end)[order]
    if np.any(forward[first[shared]] == forward[first[shared] + 1]):
        raise TopologyError("faces are not consistently oriented")
    edges = np.column_stack([unique // n_vertices, unique % n_vertices]).astype(np.int64)
    return EdgeTopology(
        edges=edges,
        keys=unique.astype(np.int64),
        face_edges=inverse.reshape(n_faces, corners).astype(np.int64),
        edge_faces=edge_faces,
        n_vertices=n_vertices,
    )


def _adjacency(pairs: IntArray, n_vertices: int) -> sp.csr_matrix:
    """Symmetric 0/1 adjacency matrix of the vertex pairs."""
    rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
    cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
    data = np.ones(len(rows))
    return sp.csr_matrix((data, (rows, cols)), shape=(n_vertices, n_vertices))


def _rows(mask: BoolArray, values: FloatArray | float = 1.0) -> sp.dia_matrix:
    """Diagonal matrix that keeps (and scales) the rows selected by `mask`."""
    return sp.diags(np.where(mask, values, 0.0))


@dataclass(frozen=True)
class VertexClasses:
    """Subdivision rule of every vertex: interior, smooth boundary or corner."""

    valence: FloatArray
    interior: BoolArray
    boundary: BoolArray
    corner: BoolArray


def _classify(faces: IntArray, topology: EdgeTopology) -> VertexClasses:
    n = topology.n_vertices
    valence = np.bincount(topology.edges.ravel(), minlength=n).astype(np.float64)
    face_count = np.bincount(faces.ravel(), minlength=n)
    boundary_count = np.bincount(topology.edges[topology.boundary].ravel(), minlength=n)
    interior = (boundary_count == 0) & (valence >= 3)
    boundary = (boundary_count == 2) & (face_count >= 2)
    return VertexClasses(valence, interior, boundary, ~(interior | boundary))


@dataclass(frozen=True)
class SubdivisionStep:
    """One Catmull-Clark step.

    Attributes:
        matrix: (n_vertices + n_edges + n_faces, n_vertices) map from coarse to fine
            positions.
        quads: (k * n_faces, 4) faces of the refined mesh; the quad of corner i of face f
            is `k * f + i`.
        topology: Edges of the coarse mesh.
    """

    matrix: sp.csr_matrix
    quads: IntArray
    topology: EdgeTopology


def catmull_clark(faces: IntArray, n_vertices: int) -> SubdivisionStep:
    """One subdivision step of a mesh whose faces all have k corners (triangles or quads)."""
    topology = edge_topology(faces, n_vertices)
    n_faces, corners = faces.shape
    n_edges = len(topology.edges)
    face_ids = np.repeat(np.arange(n_faces), corners)

    face_points = sp.csr_matrix(
        (np.full(n_faces * corners, 1.0 / corners), (face_ids, faces.ravel())),
        shape=(n_faces, n_vertices),
    )

    boundary_edge = topology.boundary
    edge_ids = np.repeat(np.arange(n_edges), 2)
    midpoints = sp.csr_matrix(
        (np.full(2 * n_edges, 0.5), (edge_ids, topology.edges.ravel())),
        shape=(n_edges, n_vertices),
    )
    interior_edges = np.flatnonzero(~boundary_edge)
    edge_face_average = sp.csr_matrix(
        (
            np.full(2 * len(interior_edges), 0.5),
            (np.repeat(interior_edges, 2), topology.edge_faces[interior_edges].ravel()),
        ),
        shape=(n_edges, n_faces),
    )
    # Interior: (v0 + v1 + f_a + f_b) / 4; boundary: the midpoint.
    edge_points = _rows(boundary_edge, 1.0) @ midpoints + 0.5 * (
        _rows(~boundary_edge) @ midpoints + edge_face_average @ face_points
    )

    classes = _classify(faces, topology)
    valence = np.maximum(classes.valence, 1.0)
    adjacency = _adjacency(topology.edges, n_vertices)
    vertex_faces = sp.csr_matrix(
        (np.ones(n_faces * corners), (faces.ravel(), face_ids)), shape=(n_vertices, n_faces)
    )
    # Interior vertex of valence n: (n - 2)/n v + (sum of neighbours + sum of face points)/n^2.
    interior_rule = sp.diags((valence - 2.0) / valence) + sp.diags(1.0 / valence**2) @ (
        adjacency + vertex_faces @ face_points
    )
    boundary_rule = 0.75 * sp.identity(n_vertices) + 0.125 * _adjacency(
        topology.edges[boundary_edge], n_vertices
    )
    vertex_points = (
        _rows(classes.interior) @ interior_rule
        + _rows(classes.boundary) @ boundary_rule
        + _rows(classes.corner)
    )

    matrix = sp.vstack([vertex_points, edge_points, face_points]).tocsr()
    matrix.eliminate_zeros()
    face_centres = n_vertices + n_edges + face_ids.reshape(n_faces, corners)
    quads = np.stack(
        [
            faces,
            n_vertices + topology.face_edges,
            face_centres,
            n_vertices + np.roll(topology.face_edges, 1, axis=1),
        ],
        axis=2,
    ).reshape(-1, 4)
    return SubdivisionStep(matrix=matrix, quads=quads.astype(np.int64), topology=topology)


def limit_matrix(quads: IntArray, n_vertices: int) -> sp.csr_matrix:
    """Limit positions of the vertices of an all-quad mesh (one row per vertex).

    Interior vertex of valence n: (n^2 v + 4 sum(edge neighbours) + sum(diagonal
    neighbours)) / (n (n + 5)); smooth boundary vertex: (b0 + 4 v + b1) / 6; corners stay.
    """
    topology = edge_topology(quads, n_vertices)
    classes = _classify(quads, topology)
    n = np.maximum(classes.valence, 1.0)
    adjacency = _adjacency(topology.edges, n_vertices)
    diagonal = sp.csr_matrix(
        (
            np.ones(4 * len(quads)),
            (quads.ravel(), np.roll(quads, -2, axis=1).ravel()),
        ),
        shape=(n_vertices, n_vertices),
    )
    scale = 1.0 / (n * (n + 5.0))
    interior_rule = sp.diags(n**2 * scale) + sp.diags(scale) @ (4.0 * adjacency + diagonal)
    boundary_rule = (
        4.0 * sp.identity(n_vertices) + _adjacency(topology.edges[topology.boundary], n_vertices)
    ) / 6.0
    matrix = (
        _rows(classes.interior) @ interior_rule
        + _rows(classes.boundary) @ boundary_rule
        + _rows(classes.corner)
    ).tocsr()
    matrix.eliminate_zeros()
    return matrix


def grid_cells(grids: IntArray) -> IntArray:
    """The quads of patch grids, ordered by patch, then u, then v."""
    return np.stack(
        [grids[:, :-1, :-1], grids[:, 1:, :-1], grids[:, 1:, 1:], grids[:, :-1, 1:]], axis=-1
    ).reshape(-1, 4)


@dataclass(frozen=True)
class PatchHierarchy:
    """Subdivision of a quad control cage down to a regular sample grid per cage quad.

    Attributes:
        steps: Subdivision matrices, coarse to fine.
        limit: Limit-position matrix of the finest level.
        grids: (p, m + 1, m + 1) vertex indices of every patch at the finest level.
        n_vertices: Vertex count of the finest level.
    """

    steps: tuple[sp.csr_matrix, ...]
    limit: sp.csr_matrix
    grids: IntArray
    n_vertices: int

    @property
    def cells(self) -> IntArray:
        return grid_cells(self.grids)

    def limit_points(self, cage: FloatArray) -> FloatArray:
        """Limit positions of every fine vertex for cage positions (n, 3)."""
        positions = cage
        for step in self.steps:
            positions = step @ positions
        result: FloatArray = self.limit @ positions
        return result

    def sample_matrix(self) -> sp.csr_matrix:
        """The composite map from cage vertices to limit samples (for least squares)."""
        matrix = self.limit
        for step in reversed(self.steps):
            matrix = matrix @ step
        return matrix.tocsr()


def patch_hierarchy(quads: IntArray, n_vertices: int, levels: int) -> PatchHierarchy:
    """Refine every quad of the cage `levels` times; the grids get 2^levels + 1 samples."""
    grids = np.stack(
        [np.stack([quads[:, 0], quads[:, 3]], -1), np.stack([quads[:, 1], quads[:, 2]], -1)],
        axis=1,
    ).astype(np.int64)
    steps: list[sp.csr_matrix] = []
    count = n_vertices
    for _ in range(levels):
        step = catmull_clark(grid_cells(grids), count)
        n_edges = len(step.topology.edges)
        patches, size, _ = grids.shape
        cells = size - 1
        refined = np.empty((patches, 2 * cells + 1, 2 * cells + 1), dtype=np.int64)
        refined[:, ::2, ::2] = grids
        refined[:, 1::2, ::2] = count + step.topology.edge_ids(grids[:, :-1, :], grids[:, 1:, :])
        refined[:, ::2, 1::2] = count + step.topology.edge_ids(grids[:, :, :-1], grids[:, :, 1:])
        refined[:, 1::2, 1::2] = (
            count + n_edges + np.arange(patches * cells * cells).reshape(patches, cells, cells)
        )
        steps.append(step.matrix)
        grids = refined
        count = step.matrix.shape[0]
    limit = limit_matrix(grid_cells(grids), count)
    return PatchHierarchy(steps=tuple(steps), limit=limit, grids=grids, n_vertices=count)


def quad_vertex_normals(positions: FloatArray, quads: IntArray) -> FloatArray:
    """Area-weighted unit normals of the vertices of an outward-oriented quad mesh."""
    p = positions
    face_normals = np.cross(p[quads[:, 2]] - p[quads[:, 0]], p[quads[:, 3]] - p[quads[:, 1]])
    normals = np.zeros_like(positions)
    for corner in range(4):
        for axis in range(3):
            normals[:, axis] += np.bincount(
                quads[:, corner], weights=face_normals[:, axis], minlength=len(positions)
            )
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    result: FloatArray = normals / np.maximum(length, 1e-300)
    return result
