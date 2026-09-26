"""Mesh preparation: repair, small parts, hole filling, face deletion.

Every operation returns the new mesh, an exact face index map `new_to_old`
(see `m2c_kernel.mesh.remap`), a flag per new face that marks faces created by
the step, and counts for the report. Methods and measurements:
`.work/research/algorithms-mesh.md` 1.2-1.4.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

from m2c_kernel.mesh.load import RawMesh, weld_vertices
from m2c_kernel.mesh.topology import EdgeTopology, edge_topology, pack_rows

type RepairStep = Literal["weld", "degenerate", "duplicates", "winding", "orientation"]
REPAIR_STEPS: tuple[RepairStep, ...] = (
    "weld",
    "degenerate",
    "duplicates",
    "winding",
    "orientation",
)

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class MeshChange:
    """Result of a preparation step.

    Attributes:
        mesh: The new mesh.
        new_to_old: Source face of every new face, -1 for faces without a source.
        synthetic: True for faces created by the step (hole filling).
        counts: Numbers for the report, keyed by i18n-friendly names.
    """

    mesh: RawMesh
    new_to_old: IntArray
    synthetic: BoolArray
    counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def identity(cls, mesh: RawMesh) -> MeshChange:
        n = len(mesh.faces)
        return cls(mesh, np.arange(n, dtype=np.int64), np.zeros(n, dtype=bool))

    def then(self, step: MeshChange) -> MeshChange:
        """Chain a step applied to `self.mesh`: maps and counts are composed."""
        has_source = step.new_to_old >= 0
        source = np.where(has_source, step.new_to_old, 0)
        new_to_old = np.where(has_source, self.new_to_old[source], -1)
        synthetic = np.where(has_source, self.synthetic[source], step.synthetic)
        return MeshChange(step.mesh, new_to_old, synthetic, {**self.counts, **step.counts})


def repair(mesh: RawMesh, steps: Collection[RepairStep] = REPAIR_STEPS) -> MeshChange:
    """Weld, drop degenerate and duplicate faces, fix winding, orient outward."""
    change = MeshChange.identity(mesh)
    if "weld" in steps:
        welded, merged = weld_vertices(mesh)
        change = MeshChange(welded, change.new_to_old, change.synthetic, {"mergedVertices": merged})
    if "degenerate" in steps:
        change = change.then(remove_degenerate_faces(change.mesh))
    if "duplicates" in steps:
        change = change.then(remove_duplicate_faces(change.mesh))
    if "winding" in steps:
        change = change.then(fix_winding(change.mesh))
    if "orientation" in steps:
        change = change.then(orient_outward(change.mesh))
    return _without_unused_vertices(change)


def remove_degenerate_faces(mesh: RawMesh) -> MeshChange:
    """Drop faces with a repeated vertex index or (numerically) zero area."""
    v, f = mesh.vertices, mesh.faces
    repeated = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    diagonal = float(np.linalg.norm(np.ptp(v, axis=0))) if len(v) else 0.0
    tiny = 0.5 * np.linalg.norm(cross, axis=1) <= (1e-9 * diagonal) ** 2
    keep = np.flatnonzero(~(repeated | tiny))
    return _kept(mesh, keep, {"degenerateFaces": len(f) - len(keep)})


def remove_duplicate_faces(mesh: RawMesh) -> MeshChange:
    """Drop faces that use the same three vertices as an earlier face (in any winding)."""
    if len(mesh.faces) == 0:
        return _kept(mesh, np.arange(0, dtype=np.int64), {"duplicateFaces": 0})
    _, first = np.unique(pack_rows(np.sort(mesh.faces, axis=1)), return_index=True)
    keep = np.sort(first).astype(np.int64)
    return _kept(mesh, keep, {"duplicateFaces": len(mesh.faces) - len(keep)})


def fix_winding(mesh: RawMesh, topology: EdgeTopology | None = None) -> MeshChange:
    """Make the orientation consistent within every manifold-connected component.

    Double cover: node i is face i as is, node i + n face i flipped. Consistent
    neighbours connect (i, j) and (i + n, j + n), inconsistent ones (i, j + n) and
    (i + n, j). A face is flipped when its flipped copy lies in the same double-cover
    component as its component's first face; faces where both copies do are
    non-orientable and stay as they are.
    """
    faces = mesh.faces
    n = len(faces)
    if n == 0:
        return _unchanged(mesh, {"flippedFaces": 0, "nonOrientableFaces": 0})
    topology = edge_topology(faces) if topology is None else topology
    face_a, face_b = topology.face_pairs.T
    pairs = topology.paired_half_edges
    inconsistent = topology.half_edges[pairs[:, 0], 0] == topology.half_edges[pairs[:, 1], 0]
    rows = np.concatenate([face_a, face_a + n])
    cols = np.concatenate(
        [np.where(inconsistent, face_b + n, face_b), np.where(inconsistent, face_b, face_b + n)]
    )
    ones = np.ones(len(rows), dtype=np.int8)
    _, cover = connected_components(sp.coo_matrix((ones, (rows, cols)), shape=(2 * n, 2 * n)))
    plain = sp.coo_matrix((ones[: len(face_a)], (face_a, face_b)), shape=(n, n))
    _, component = connected_components(plain, directed=False)
    root = np.unique(component, return_index=True)[1]
    root_label = cover[root][component]
    flip = cover[n:] == root_label
    non_orientable = flip & (cover[:n] == root_label)
    flip &= ~non_orientable
    new_faces = faces.copy()
    new_faces[flip] = faces[flip, ::-1]
    counts = {"flippedFaces": int(flip.sum()), "nonOrientableFaces": int(non_orientable.sum())}
    return _unchanged(RawMesh(mesh.vertices, new_faces), counts)


def signed_volume(mesh: RawMesh) -> float:
    """Signed enclosed volume (exact for closed meshes, an orientation hint for open ones)."""
    v, f = mesh.vertices, mesh.faces
    centre = v.mean(axis=0)
    a, b, c = v[f[:, 0]] - centre, v[f[:, 1]] - centre, v[f[:, 2]] - centre
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def orient_outward(mesh: RawMesh) -> MeshChange:
    """Flip every face when the signed volume is negative (normals point inward)."""
    if len(mesh.faces) and signed_volume(mesh) < 0:
        return _unchanged(RawMesh(mesh.vertices, mesh.faces[:, ::-1].copy()), {"inverted": 1})
    return _unchanged(mesh, {"inverted": 0})


def component_labels(mesh: RawMesh) -> tuple[int, IntArray]:
    """Number of vertex-connected components and the component of every face."""
    f = mesh.faces
    if len(f) == 0:
        return 0, np.zeros(0, dtype=np.int64)
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]]])
    ones = np.ones(len(edges), dtype=np.int8)
    n_vertices = len(mesh.vertices)
    graph = sp.coo_matrix((ones, (edges[:, 0], edges[:, 1])), shape=(n_vertices, n_vertices))
    count, labels = connected_components(graph, directed=False)
    return int(count), labels[f[:, 0]].astype(np.int64)


def remove_small_parts(mesh: RawMesh, min_ratio: float = 0.01, min_faces: int = 100) -> MeshChange:
    """Remove connected components smaller than `min_ratio` of the largest one or `min_faces`."""
    count, face_component = component_labels(mesh)
    if count == 0:
        return _unchanged(mesh, {"removedParts": 0, "removedFaces": 0})
    sizes = np.bincount(face_component, minlength=count)
    largest = int(sizes.max())
    threshold = min(max(float(min_faces), min_ratio * largest), float(largest))
    keep_component = sizes >= threshold
    keep = np.flatnonzero(keep_component[face_component])
    counts = {
        "removedParts": int(count - keep_component.sum()),
        "removedFaces": int(len(mesh.faces) - len(keep)),
    }
    return _without_unused_vertices(_kept(mesh, keep, counts))


def delete_faces(mesh: RawMesh, faces: npt.ArrayLike) -> MeshChange:
    """Delete the given faces and the vertices no other face uses."""
    remove = np.zeros(len(mesh.faces), dtype=bool)
    remove[np.asarray(faces, dtype=np.int64)] = True
    keep = np.flatnonzero(~remove)
    return _without_unused_vertices(_kept(mesh, keep, {"deletedFaces": int(remove.sum())}))


@dataclass(frozen=True)
class BoundaryLoops:
    loops: list[IntArray]
    skipped: int


def boundary_loops(mesh: RawMesh, topology: EdgeTopology | None = None) -> BoundaryLoops:
    """Ordered boundary loops; loops through a bow-tie vertex are skipped and counted."""
    topology = edge_topology(mesh.faces) if topology is None else topology
    boundary = topology.boundary_half_edges
    if len(boundary) == 0:
        return BoundaryLoops([], 0)
    n_vertices = len(mesh.vertices)
    out_degree = np.bincount(boundary[:, 0], minlength=n_vertices)
    successor = np.full(n_vertices, -1, dtype=np.int64)
    successor[boundary[:, 0]] = boundary[:, 1]
    vertices = np.unique(boundary)
    local = np.searchsorted(vertices, boundary)
    ones = np.ones(len(boundary), dtype=np.int8)
    size = len(vertices)
    graph = sp.coo_matrix((ones, (local[:, 0], local[:, 1])), shape=(size, size))
    _, label = connected_components(graph, directed=False)
    complex_loops = set(np.unique(label[out_degree[vertices] > 1]).tolist())
    loops: list[IntArray] = []
    for loop_label, first in zip(*np.unique(label, return_index=True), strict=True):
        if int(loop_label) in complex_loops:
            continue
        start = int(vertices[first])
        loop = [start]
        vertex = int(successor[start])
        while vertex != start and len(loop) <= size:
            loop.append(vertex)
            vertex = int(successor[vertex])
        if vertex == start:
            loops.append(np.asarray(loop, dtype=np.int64))
    return BoundaryLoops(loops, len(complex_loops))


def fill_holes(mesh: RawMesh, max_perimeter: float) -> MeshChange:
    """Close holes with a perimeter up to `max_perimeter` millimetres by a centroid fan.

    A boundary half-edge a->b borders a face that uses a->b, so the new triangle uses
    b->a to keep the winding consistent. Larger holes stay open: a fan over a large
    opening would invent a surface, and open areas do not disturb fitting.
    """
    found = boundary_loops(mesh)
    new_vertices: list[npt.NDArray[np.float64]] = []
    new_faces: list[IntArray] = []
    base = len(mesh.vertices)
    for loop in found.loops:
        points = mesh.vertices[loop]
        perimeter = float(np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).sum())
        if perimeter > max_perimeter:
            continue
        centre = base + len(new_vertices)
        new_vertices.append(points.mean(axis=0))
        following = np.roll(loop, -1)
        new_faces.append(np.stack([following, loop, np.full(len(loop), centre)], axis=1))
    filled = len(new_faces)
    added = sum(len(item) for item in new_faces)
    counts = {
        "filledHoles": filled,
        "openHoles": len(found.loops) - filled + found.skipped,
        "addedFaces": added,
    }
    if filled == 0:
        return _unchanged(mesh, counts)
    vertices = np.vstack([mesh.vertices, np.asarray(new_vertices)])
    faces = np.vstack([mesh.faces, *new_faces])
    old = len(mesh.faces)
    new_to_old = np.concatenate([np.arange(old, dtype=np.int64), np.full(added, -1, np.int64)])
    synthetic = np.concatenate([np.zeros(old, dtype=bool), np.ones(added, dtype=bool)])
    return MeshChange(RawMesh(vertices, faces), new_to_old, synthetic, counts)


def smooth_for_display(mesh: RawMesh, iterations: int) -> npt.NDArray[np.float64]:
    """Taubin-smoothed vertex positions for display and scan export; never used for fitting."""
    vertices = np.asarray(mesh.vertices, dtype=np.float64).copy()
    if iterations <= 0 or len(mesh.faces) == 0:
        return vertices
    f = mesh.faces
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    n = len(vertices)
    adjacency = sp.coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    adjacency = adjacency.tocsr()
    adjacency.data[:] = 1.0
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    average = sp.diags(1.0 / np.maximum(degree, 1.0)) @ adjacency
    for _ in range(iterations):
        vertices += 0.5 * (average @ vertices - vertices)
        vertices += -0.53 * (average @ vertices - vertices)
    return vertices


def _kept(mesh: RawMesh, keep: IntArray, counts: dict[str, int]) -> MeshChange:
    return MeshChange(
        RawMesh(mesh.vertices, mesh.faces[keep]), keep, np.zeros(len(keep), dtype=bool), counts
    )


def _unchanged(mesh: RawMesh, counts: dict[str, int]) -> MeshChange:
    n = len(mesh.faces)
    return MeshChange(mesh, np.arange(n, dtype=np.int64), np.zeros(n, dtype=bool), counts)


def _compacted(mesh: RawMesh) -> MeshChange:
    """Drop unreferenced vertices; faces keep their order."""
    used = np.zeros(len(mesh.vertices), dtype=bool)
    used[mesh.faces.ravel()] = True
    new_index = np.cumsum(used) - 1
    compacted = RawMesh(mesh.vertices[used], new_index[mesh.faces].astype(np.int64))
    return _unchanged(compacted, {})


def _without_unused_vertices(change: MeshChange) -> MeshChange:
    return change.then(_compacted(change.mesh))
