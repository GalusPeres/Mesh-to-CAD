"""Edge topology and face adjacency of triangle meshes.

The edge topology is built once from a single argsort over all half-edges and is
reused by winding repair, boundary loops, hole filling and the face graph used
for region growing. Measurements: `.work/research/algorithms-mesh.md` 1.2 and 2.3.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


def pack_rows(rows: npt.ArrayLike) -> npt.NDArray[np.generic]:
    """Encode each row of non-negative integers as one int64, a fast `np.unique` key.

    Falls back to a void view when the columns need more than 63 bits together.
    """
    array = np.asarray(rows, dtype=np.int64)
    array = array - array.min(axis=0)
    bits = [max(int(m).bit_length(), 1) for m in array.max(axis=0)]
    if sum(bits) > 63:
        packed: npt.NDArray[np.generic] = np.ascontiguousarray(array).view(f"V{8 * array.shape[1]}")
        return packed.ravel()
    key = np.zeros(len(array), dtype=np.int64)
    for column, width in zip(array.T, bits, strict=True):
        key = (key << width) | column
    return key


@dataclass(frozen=True)
class EdgeTopology:
    """Half-edge to edge map of a triangle mesh.

    Half-edge `k` is edge `(v0v1, v1v2, v2v0)[k // n_faces]` of face `k % n_faces`.

    Attributes:
        half_edges: (3F, 2) directed half-edges.
        edge_of_half_edge: (3F,) undirected edge id of every half-edge.
        valence: (E,) faces per edge: 1 = boundary, 2 = manifold, more = non-manifold.
        paired_half_edges: (M, 2) the two half-edges of every manifold edge.
        face_count: Number of faces.
    """

    half_edges: IntArray
    edge_of_half_edge: IntArray
    valence: IntArray
    paired_half_edges: IntArray
    face_count: int

    @property
    def face_pairs(self) -> IntArray:
        """(M, 2) faces adjacent across every manifold edge."""
        return self.paired_half_edges % self.face_count

    @property
    def boundary_half_edges(self) -> IntArray:
        boundary: IntArray = self.half_edges[self.valence[self.edge_of_half_edge] == 1]
        return boundary

    @property
    def non_manifold_edge_count(self) -> int:
        return int((self.valence > 2).sum())

    def inconsistent_edge_count(self) -> int:
        """Manifold edges whose two faces traverse them in the same direction."""
        pairs = self.paired_half_edges
        return int((self.half_edges[pairs[:, 0], 0] == self.half_edges[pairs[:, 1], 0]).sum())


def edge_topology(faces: npt.ArrayLike) -> EdgeTopology:
    """Build the edge topology of (F, 3) faces."""
    f = np.asarray(faces, dtype=np.int64)
    half_edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    low = np.minimum(half_edges[:, 0], half_edges[:, 1])
    high = np.maximum(half_edges[:, 0], half_edges[:, 1])
    key = low * (int(f.max()) + 1) + high
    order = np.argsort(key, kind="stable")
    sorted_keys = key[order]
    starts_edge = np.empty(len(sorted_keys), dtype=bool)
    starts_edge[0] = True
    starts_edge[1:] = sorted_keys[1:] != sorted_keys[:-1]
    edge_sorted = np.cumsum(starts_edge) - 1
    edge_of_half_edge = np.empty_like(edge_sorted)
    edge_of_half_edge[order] = edge_sorted
    valence = np.bincount(edge_sorted)
    starts = np.flatnonzero(starts_edge)
    manifold = valence == 2
    paired = np.stack([order[starts[manifold]], order[starts[manifold] + 1]], axis=1)
    return EdgeTopology(half_edges, edge_of_half_edge, valence, paired, len(f))


class FaceGraph:
    """Edge adjacency of faces as an (F, 3) neighbour table (-1 = open or non-manifold edge).

    A wave-by-wave breadth-first search on the table costs a few numpy calls per
    ring and accepts a new face mask per call without rebuilding a sparse matrix.
    """

    def __init__(self, topology: EdgeTopology) -> None:
        n = topology.face_count
        self.face_count = n
        self.pairs = topology.face_pairs
        he_a, he_b = topology.paired_half_edges[:, 0], topology.paired_half_edges[:, 1]
        face_a, slot_a, face_b, slot_b = he_a % n, he_a // n, he_b % n, he_b // n
        self.neighbours = np.full((n, 3), -1, dtype=np.int64)
        self.pair_of_slot = np.full((n, 3), -1, dtype=np.int64)
        self.neighbours[face_a, slot_a] = face_b
        self.neighbours[face_b, slot_b] = face_a
        pair_index = np.arange(len(he_a))
        self.pair_of_slot[face_a, slot_a] = pair_index
        self.pair_of_slot[face_b, slot_b] = pair_index

    def grow(
        self,
        seeds: npt.ArrayLike,
        allowed: BoolArray | None = None,
        pair_allowed: BoolArray | None = None,
        max_rings: int | None = None,
    ) -> BoolArray:
        """Faces reachable from the seeds through allowed faces and allowed edges."""
        region = np.zeros(self.face_count, dtype=bool)
        frontier = np.atleast_1d(np.asarray(seeds, dtype=np.int64))
        region[frontier] = True
        ring = 0
        while len(frontier) and (max_rings is None or ring < max_rings):
            candidates = self.neighbours[frontier]
            ok = candidates >= 0
            if pair_allowed is not None:
                ok &= pair_allowed[np.where(ok, self.pair_of_slot[frontier], 0)]
            reached = candidates[ok]
            if allowed is not None:
                reached = reached[allowed[reached]]
            frontier = np.unique(reached[~region[reached]])
            region[frontier] = True
            ring += 1
        return region

    def components(self, allowed: BoolArray) -> IntArray:
        """Connected-component label per allowed face (-1 elsewhere)."""
        ok = allowed[self.pairs[:, 0]] & allowed[self.pairs[:, 1]]
        a, b = self.pairs[ok, 0], self.pairs[ok, 1]
        weights = np.ones(2 * len(a), dtype=np.int8)
        graph = sp.csr_matrix(
            (weights, (np.r_[a, b], np.r_[b, a])), shape=(self.face_count, self.face_count)
        )
        _, labels = connected_components(graph, directed=False)
        result: IntArray = np.where(allowed, labels, -1)
        return result
