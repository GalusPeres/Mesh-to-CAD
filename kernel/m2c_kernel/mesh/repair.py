"""Mesh preparation: repair, small parts, hole filling, face deletion.

Every operation returns a `MeshChange`: the new mesh, an exact face index map
`new_to_old` (see `m2c_kernel.mesh.remap`), a flag per new face that marks faces
created by the step, and counts for the report. Methods and measurements:
`.work/research/algorithms-mesh.md` 1.2.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

from m2c_kernel.geometry import FloatArray
from m2c_kernel.mesh.load import RawMesh, compact, weld_vertices
from m2c_kernel.mesh.topology import EdgeTopology, edge_topology, pack_rows

type RepairStep = Literal["weld", "degenerate", "duplicates", "winding", "orientation"]
REPAIR_STEPS: tuple[RepairStep, ...] = (
    "weld",
    "degenerate",
    "duplicates",
    "winding",
    "orientation",
)

DEFAULT_MIN_PART_RATIO = 0.01
DEFAULT_MIN_PART_FACES = 100

ORIENTATION_CERTAINTY = 0.2
"""A part is turned outward only when its signed volume is at least this share of the
unsigned sum of its volume contributions. Closed and mostly closed parts reach 0.9 and
more; a single-sided patch stays far below and is left as it is."""

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class MeshChange:
    """Result of a preparation step.

    Attributes:
        mesh: The new mesh.
        new_to_old: Source face of every new face, -1 for faces without a source.
        synthetic: True for faces created by the step (hole filling).
        counts: Numbers for the report; the keys are i18n keys of the mesh tools.
        affected: Faces of the input that the step removes, flips or borders on (the
            faces around a filled hole), sorted; a dry run shows them in the viewport.
    """

    mesh: RawMesh
    new_to_old: IntArray
    synthetic: BoolArray
    counts: dict[str, int] = field(default_factory=dict)
    affected: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))

    @classmethod
    def identity(
        cls,
        mesh: RawMesh,
        counts: dict[str, int] | None = None,
        affected: IntArray | None = None,
    ) -> MeshChange:
        n = len(mesh.faces)
        touched = np.zeros(0, dtype=np.int64) if affected is None else affected
        return cls(
            mesh, np.arange(n, dtype=np.int64), np.zeros(n, dtype=bool), counts or {}, touched
        )

    def then(self, step: MeshChange) -> MeshChange:
        """Chain a step applied to `self.mesh`: maps, counts and affected faces are composed."""
        has_source = step.new_to_old >= 0
        source = np.where(has_source, step.new_to_old, 0)
        new_to_old = np.where(has_source, self.new_to_old[source], -1)
        synthetic = np.where(has_source, self.synthetic[source], step.synthetic)
        earlier = self.new_to_old[step.affected]
        affected = np.union1d(self.affected, earlier[earlier >= 0])
        counts = {**self.counts, **step.counts}
        return MeshChange(step.mesh, new_to_old, synthetic, counts, affected)


def repair(mesh: RawMesh, steps: Collection[RepairStep] = REPAIR_STEPS) -> MeshChange:
    """Weld, drop degenerate and duplicate faces, fix winding, orient parts outward."""
    change = MeshChange.identity(mesh)
    if "weld" in steps:
        welded, merged = weld_vertices(mesh)
        change = MeshChange(welded, change.new_to_old, change.synthetic, {"mergedVertices": merged})
    if "degenerate" in steps:
        change = change.then(remove_degenerate_faces(change.mesh))
    if "duplicates" in steps:
        change = change.then(remove_duplicate_faces(change.mesh))
    if len(change.mesh.faces) and ("winding" in steps or "orientation" in steps):
        # Flipping faces keeps the edge pairing, so both steps share one topology.
        topology = edge_topology(change.mesh.faces)
        if "winding" in steps:
            change = change.then(fix_winding(change.mesh, topology))
        if "orientation" in steps:
            change = change.then(orient_outward(change.mesh, topology))
    return _without_unused_vertices(change)


def remove_degenerate_faces(mesh: RawMesh) -> MeshChange:
    """Drop faces with a repeated vertex index or an area of (numerically) zero."""
    v, f = mesh.vertices, mesh.faces
    repeated = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    doubled_area = np.linalg.norm(
        np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1
    )
    diagonal = float(np.linalg.norm(np.ptp(v, axis=0))) if len(v) else 0.0
    zero_area = doubled_area <= 2.0 * (1e-9 * diagonal) ** 2
    keep = np.flatnonzero(~(repeated | zero_area))
    return _kept(mesh, keep, {"degenerateFaces": len(f) - len(keep)})


def remove_duplicate_faces(mesh: RawMesh) -> MeshChange:
    """Drop faces that use the same three vertices as an earlier face, in either winding."""
    if len(mesh.faces) == 0:
        return MeshChange.identity(mesh, {"duplicateFaces": 0})
    _, first = np.unique(pack_rows(np.sort(mesh.faces, axis=1)), return_index=True)
    keep = np.sort(first).astype(np.int64)
    return _kept(mesh, keep, {"duplicateFaces": len(mesh.faces) - len(keep)})


def fix_winding(mesh: RawMesh, topology: EdgeTopology | None = None) -> MeshChange:
    """Make the orientation consistent within every edge-connected part.

    Double cover: node i is face i as is, node i + n face i flipped. Consistent
    neighbours connect (i, j) and (i + n, j + n), inconsistent ones (i, j + n) and
    (i + n, j). Faces whose flipped copy lies in the same double-cover component
    as the part's first face disagree with it; the smaller of the two groups is
    flipped, so the count is the number of faces that were really wrong. Faces
    where both copies are connected are non-orientable and stay as they are.
    Which way the part faces is decided afterwards by `orient_outward`.
    """
    faces = mesh.faces
    n = len(faces)
    if n == 0:
        return MeshChange.identity(mesh, {"flippedFaces": 0, "nonOrientableFaces": 0})
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
    part = face_components(topology)
    root = np.unique(part, return_index=True)[1]
    root_label = cover[root][part]
    flip = cover[n:] == root_label
    non_orientable = flip & (cover[:n] == root_label)
    flip &= ~non_orientable

    orientable = np.bincount(part, weights=~non_orientable)
    disagreeing = np.bincount(part, weights=flip, minlength=len(orientable))
    majority_wrong = disagreeing > orientable / 2
    flip ^= majority_wrong[part] & ~non_orientable

    new_faces = faces.copy()
    new_faces[flip] = faces[flip, ::-1]
    counts = {"flippedFaces": int(flip.sum()), "nonOrientableFaces": int(non_orientable.sum())}
    flipped = np.flatnonzero(flip)
    return MeshChange.identity(RawMesh(mesh.vertices, new_faces), counts, flipped)


def face_components(topology: EdgeTopology) -> IntArray:
    """Part label of every face; faces connect across manifold edges."""
    n = topology.face_count
    face_a, face_b = topology.face_pairs.T
    ones = np.ones(len(face_a), dtype=np.int8)
    _, labels = connected_components(
        sp.coo_matrix((ones, (face_a, face_b)), shape=(n, n)), directed=False
    )
    part: IntArray = labels.astype(np.int64)
    return part


def signed_volume(mesh: RawMesh) -> float:
    """Signed enclosed volume (exact for closed meshes, an orientation hint for open ones)."""
    v, f = mesh.vertices, mesh.faces
    centre = v.mean(axis=0)
    a, b, c = v[f[:, 0]] - centre, v[f[:, 1]] - centre, v[f[:, 2]] - centre
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def orient_outward(mesh: RawMesh, topology: EdgeTopology | None = None) -> MeshChange:
    """Turn every part whose normals point inward, judged by its signed volume.

    The volume of each part is taken about its own centroid. Parts whose sign is
    not clear (`ORIENTATION_CERTAINTY`), such as a scan of one side of a relief,
    are left unchanged: there is no inside to point away from.
    """
    v, f = mesh.vertices, mesh.faces
    if len(f) == 0:
        return MeshChange.identity(mesh, {"invertedParts": 0})
    topology = edge_topology(f) if topology is None else topology
    part = face_components(topology)
    count = int(part.max()) + 1
    corners = v[f]
    face_centre = corners.mean(axis=1)
    sizes = np.bincount(part, minlength=count)
    sums = [np.bincount(part, weights=face_centre[:, axis], minlength=count) for axis in range(3)]
    centre = np.stack(sums, axis=1) / sizes[:, None]
    relative = corners - centre[part][:, None, :]
    contribution = np.einsum("ij,ij->i", relative[:, 0], np.cross(relative[:, 1], relative[:, 2]))
    volume = np.bincount(part, weights=contribution, minlength=count)
    spread = np.bincount(part, weights=np.abs(contribution), minlength=count)
    inverted = (volume < 0) & (np.abs(volume) >= ORIENTATION_CERTAINTY * spread)
    if not inverted.any():
        return MeshChange.identity(mesh, {"invertedParts": 0})
    flip = inverted[part]
    new_faces = f.copy()
    new_faces[flip] = f[flip, ::-1]
    counts = {"invertedParts": int(inverted.sum())}
    return MeshChange.identity(RawMesh(v, new_faces), counts, np.flatnonzero(flip))


def component_labels(mesh: RawMesh) -> tuple[int, IntArray]:
    """Number of vertex-connected components and the component of every face."""
    f = mesh.faces
    if len(f) == 0:
        return 0, np.zeros(0, dtype=np.int64)
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]]])
    ones = np.ones(len(edges), dtype=np.int8)
    n_vertices = len(mesh.vertices)
    graph = sp.coo_matrix((ones, (edges[:, 0], edges[:, 1])), shape=(n_vertices, n_vertices))
    _, labels = connected_components(graph, directed=False)
    used = np.unique(labels[f[:, 0]], return_inverse=True)[1]
    return int(used.max()) + 1, used.reshape(-1).astype(np.int64)


def remove_small_parts(
    mesh: RawMesh,
    min_ratio: float = DEFAULT_MIN_PART_RATIO,
    min_faces: int = DEFAULT_MIN_PART_FACES,
) -> MeshChange:
    """Remove loose parts below `min_ratio` of the largest part or below `min_faces` faces.

    The largest part is always kept. Keeping only the largest part would delete
    legitimate separate bodies of a multi-part scan.
    """
    count, face_part = component_labels(mesh)
    if count == 0:
        return MeshChange.identity(mesh, {"removedParts": 0, "removedFaces": 0})
    keep_part = parts_to_keep(np.bincount(face_part, minlength=count), min_ratio, min_faces)
    keep = np.flatnonzero(keep_part[face_part])
    counts = {
        "removedParts": int(count - keep_part.sum()),
        "removedFaces": int(len(mesh.faces) - len(keep)),
    }
    return _without_unused_vertices(_kept(mesh, keep, counts))


def parts_to_keep(
    sizes: IntArray,
    min_ratio: float = DEFAULT_MIN_PART_RATIO,
    min_faces: int = DEFAULT_MIN_PART_FACES,
) -> BoolArray:
    """Which parts (face counts `sizes`) reach both limits; the largest part always does."""
    largest = float(sizes.max())
    threshold = min(max(float(min_faces), min_ratio * largest), largest)
    keep: BoolArray = sizes >= threshold
    return keep


def delete_faces(mesh: RawMesh, faces: npt.ArrayLike) -> MeshChange:
    """Delete the given faces and the vertices no other face uses."""
    remove = np.zeros(len(mesh.faces), dtype=bool)
    remove[np.asarray(faces, dtype=np.int64)] = True
    keep = np.flatnonzero(~remove)
    return _without_unused_vertices(_kept(mesh, keep, {"deletedFaces": int(remove.sum())}))


@dataclass(frozen=True)
class BoundaryLoops:
    """Ordered boundary loops and the number of loops through bow-tie vertices."""

    loops: list[IntArray]
    skipped: int


def boundary_loops(mesh: RawMesh, topology: EdgeTopology | None = None) -> BoundaryLoops:
    """Ordered boundary loops; loops through a bow-tie vertex are skipped and counted.

    On a manifold boundary every vertex has exactly one outgoing boundary
    half-edge, which defines the successor of the vertex along the loop.
    """
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


def loop_perimeter(vertices: FloatArray, loop: IntArray) -> float:
    points = vertices[loop]
    return float(np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).sum())


def fill_holes(mesh: RawMesh, max_perimeter: float) -> MeshChange:
    """Close holes with a perimeter up to `max_perimeter` by a fan around one new vertex.

    The new vertex is placed on a quadric fitted to the surface around the hole,
    so fans on curved surfaces follow the surface instead of cutting under it
    (`_hole_centre`). A boundary half-edge a->b belongs to a face that uses a->b,
    so the new triangles use b->a and keep the winding consistent. Larger holes
    stay open: a fan over a large opening would invent a surface, and open areas
    do not disturb fitting. Loops through bow-tie vertices are skipped.
    """
    if len(mesh.faces) == 0:
        return MeshChange.identity(mesh, {"filledHoles": 0, "openHoles": 0, "addedFaces": 0})
    topology = edge_topology(mesh.faces)
    found = boundary_loops(mesh, topology)
    to_fill = [loop for loop in found.loops if loop_perimeter(mesh.vertices, loop) <= max_perimeter]
    counts = {
        "filledHoles": len(to_fill),
        "openHoles": len(found.loops) - len(to_fill) + found.skipped,
        "addedFaces": sum(len(loop) for loop in to_fill),
    }
    if not to_fill:
        return MeshChange.identity(mesh, counts)
    incidence = _vertex_faces(mesh)
    base = len(mesh.vertices)
    centres = np.array([_hole_centre(mesh, incidence, loop) for loop in to_fill])
    fans = [
        np.stack([np.roll(loop, -1), loop, np.full(len(loop), base + index)], axis=1)
        for index, loop in enumerate(to_fill)
    ]
    added = counts["addedFaces"]
    old = len(mesh.faces)
    filled = RawMesh(np.vstack([mesh.vertices, centres]), np.vstack([mesh.faces, *fans]))
    new_to_old = np.concatenate([np.arange(old, dtype=np.int64), np.full(added, -1, np.int64)])
    synthetic = np.concatenate([np.zeros(old, dtype=bool), np.ones(added, dtype=bool)])
    border = _faces_along(topology, np.concatenate(to_fill))
    return MeshChange(filled, new_to_old, synthetic, counts, border)


def _faces_along(topology: EdgeTopology, loop_vertices: IntArray) -> IntArray:
    """Faces that own a boundary half-edge starting at one of the given vertices."""
    boundary = np.flatnonzero(topology.valence[topology.edge_of_half_edge] == 1)
    starts = topology.half_edges[boundary, 0]
    faces: IntArray = np.unique(boundary[np.isin(starts, loop_vertices)] % topology.face_count)
    return faces


def _vertex_faces(mesh: RawMesh) -> sp.csr_matrix:
    """Vertex-by-face incidence matrix."""
    faces = mesh.faces
    rows = faces.ravel()
    cols = np.repeat(np.arange(len(faces)), 3)
    ones = np.ones(len(rows), dtype=np.int8)
    return sp.csr_matrix((ones, (rows, cols)), shape=(len(mesh.vertices), len(faces)))


def _hole_centre(mesh: RawMesh, incidence: sp.csr_matrix, loop: IntArray) -> FloatArray:
    """Where the fan vertex goes: the loop centroid lifted onto the surrounding surface.

    A height quadric is fitted to the vertices of all faces that touch the loop, in
    a frame whose normal is the area-weighted normal of those faces. When the fit is
    underdetermined or proposes a lift larger than half the hole radius (a thin wall
    or a fold), the plain centroid is used.
    """
    loop_points = mesh.vertices[loop]
    centroid: FloatArray = loop_points.mean(axis=0)
    around = np.unique(incidence[loop].indices)
    ring_faces = mesh.faces[around]
    corners = mesh.vertices[ring_faces]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]).sum(axis=0)
    length = float(np.linalg.norm(normal))
    points = mesh.vertices[np.unique(ring_faces)]
    if length == 0.0 or len(points) < 12:
        return centroid
    n = normal / length
    helper = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    w = np.cross(n, u)
    offsets = points - centroid
    x, y, z = offsets @ u, offsets @ w, offsets @ n
    design = np.stack([0.5 * x * x, x * y, 0.5 * y * y, x, y, np.ones_like(x)], axis=1)
    coef, _, rank, _ = np.linalg.lstsq(design, z, rcond=None)
    radius = float(np.linalg.norm(loop_points - centroid, axis=1).mean())
    lift = float(coef[5])
    if rank < 6 or abs(lift) > 0.5 * radius:
        return centroid
    lifted: FloatArray = centroid + lift * n
    return lifted


def _kept(mesh: RawMesh, keep: IntArray, counts: dict[str, int]) -> MeshChange:
    removed = np.setdiff1d(np.arange(len(mesh.faces), dtype=np.int64), keep)
    kept = RawMesh(mesh.vertices, mesh.faces[keep])
    return MeshChange(kept, keep, np.zeros(len(keep), dtype=bool), counts, removed)


def _without_unused_vertices(change: MeshChange) -> MeshChange:
    """Drop vertices no face uses; faces keep their order and indices."""
    compacted = compact(change.mesh)
    return MeshChange(
        compacted, change.new_to_old, change.synthetic, change.counts, change.affected
    )
