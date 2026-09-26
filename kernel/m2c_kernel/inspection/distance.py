"""Signed closest-point distances from scan points to a reference surface.

Seeded vertex-ring descent with one walker per (point, B-Rep face), a second pass
from B-Rep edge vertices, and the pseudo-normal sign (Baerentzen and Aanaes).
Details and measurements: `.work/research/algorithms-cad.md` section 4.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.inspection import ProgressStage
from m2c_kernel.geometry import FloatArray
from m2c_kernel.inspection.reference import ReferenceSurface

if TYPE_CHECKING:
    from m2c_kernel.session.jobs import JobContext

type IntArray = npt.NDArray[np.int64]

# Region codes of the closest point on a triangle.
INTERIOR, VERT_A, VERT_B, VERT_C, EDGE_AB, EDGE_BC, EDGE_CA = range(7)

SEEDS = 8
MAX_WALK = 32
EDGE_BAND_MM = 1.0
CHUNK = 250_000


@dataclass(frozen=True)
class Closest:
    """Per point: signed distance (positive outside), reference triangle and convergence."""

    signed: FloatArray
    triangle: IntArray
    converged: npt.NDArray[np.bool_]


def _dot(u: FloatArray, v: FloatArray) -> FloatArray:
    return np.einsum("ij,ij->i", u, v)


def closest_on_triangles(
    p: FloatArray, a: FloatArray, b: FloatArray, c: FloatArray
) -> tuple[FloatArray, IntArray]:
    """Closest point on each triangle (Ericson, RTCD 5.1.5) and its region code."""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2

    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-300, 1e-300, denom)
    v, w = vb / denom, vc / denom
    bary = np.column_stack([1 - v - w, v, w])
    region = np.full(len(p), INTERIOR, dtype=np.int64)

    def assign(mask: npt.NDArray[np.bool_], values: FloatArray, code: int) -> None:
        bary[mask] = values[mask] if values.ndim == 2 else values
        region[mask] = code

    with np.errstate(divide="ignore", invalid="ignore"):
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        assign(
            (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0),
            np.column_stack([np.zeros_like(t), 1 - t, t]),
            EDGE_BC,
        )
        t = d2 / (d2 - d6)
        assign(
            (vb <= 0) & (d2 >= 0) & (d6 <= 0),
            np.column_stack([1 - t, np.zeros_like(t), t]),
            EDGE_CA,
        )
        t = d1 / (d1 - d3)
        assign(
            (vc <= 0) & (d1 >= 0) & (d3 <= 0),
            np.column_stack([1 - t, t, np.zeros_like(t)]),
            EDGE_AB,
        )
    assign((d6 >= 0) & (d5 <= d6), np.array([0.0, 0.0, 1.0]), VERT_C)
    assign((d3 >= 0) & (d4 <= d3), np.array([0.0, 1.0, 0.0]), VERT_B)
    assign((d1 <= 0) & (d2 <= 0), np.array([1.0, 0.0, 0.0]), VERT_A)
    closest = bary[:, :1] * a + bary[:, 1:2] * b + bary[:, 2:] * c
    return closest, region


def _first_per_owner(owner: IntArray, dist: FloatArray) -> IntArray:
    """Index of the smallest distance per owner (owners in increasing order)."""
    order = np.lexsort((dist, owner))
    keep = np.ones(len(order), dtype=bool)
    keep[1:] = owner[order][1:] != owner[order][:-1]
    return order[keep]


def _closest_among(
    ref: ReferenceSurface, points: FloatArray, owner: IntArray, candidates: IntArray
) -> tuple[IntArray, FloatArray, FloatArray, IntArray]:
    t = ref.triangles[candidates]
    query = points[owner]
    closest, region = closest_on_triangles(query, t[:, 0], t[:, 1], t[:, 2])
    dist = np.linalg.norm(query - closest, axis=1)
    first = _first_per_owner(owner, dist)
    return candidates[first], dist[first], closest[first], region[first]


def _ring_of(ref: ReferenceSurface, vertices: IntArray) -> tuple[IntArray, IntArray]:
    """All triangles around each vertex, as (owner row, triangle) pairs."""
    lengths = np.diff(ref.vf_offsets)[vertices]
    starts = ref.vf_offsets[vertices]
    total = int(lengths.sum())
    position = (
        np.arange(total)
        - np.repeat(np.cumsum(lengths) - lengths, lengths)
        + np.repeat(starts, lengths)
    )
    return np.repeat(np.arange(len(vertices)), lengths), ref.vf_faces[position]


def _vertex_ring(ref: ReferenceSurface, triangles: IntArray) -> tuple[IntArray, IntArray]:
    """All triangles around the three vertices of each triangle."""
    owner, ring = _ring_of(ref, ref.faces[triangles].ravel())
    return owner // 3, ring


def _walk(
    ref: ReferenceSurface, p: FloatArray, tri: IntArray
) -> tuple[IntArray, FloatArray, FloatArray, IntArray, npt.NDArray[np.bool_]]:
    """Greedy descent over vertex rings until the closest point is interior or stable."""
    tri, dist, closest, region = _closest_among(ref, p, np.arange(len(p)), tri)
    active = np.flatnonzero(region != INTERIOR)
    for _ in range(MAX_WALK):
        if len(active) == 0:
            break
        ring_owner, ring = _vertex_ring(ref, tri[active])
        t2, d2, c2, r2 = _closest_among(ref, p[active], ring_owner, ring)
        moved = (t2 != tri[active]) & (d2 < dist[active] - 1e-12)
        tri[active], dist[active], closest[active], region[active] = t2, d2, c2, r2
        active = active[moved & (r2 != INTERIOR)]
    stuck = np.zeros(len(p), dtype=bool)
    stuck[active] = True
    return tri, dist, closest, region, stuck


def _best_from_seeds(
    ref: ReferenceSurface, p: FloatArray, owner: IntArray, seed: IntArray
) -> tuple[IntArray, FloatArray, FloatArray, IntArray, npt.NDArray[np.bool_]]:
    """One walker per (point, B-Rep face) from its first seed; the best result per point."""
    key = owner.astype(np.int64) * (int(ref.face_id.max()) + 1) + ref.face_id[seed]
    _, first = np.unique(key, return_index=True)
    walker_owner = owner[first]
    tri, dist, closest, region, stuck = _walk(ref, p[walker_owner], seed[first])
    best = _first_per_owner(walker_owner, dist)
    return tri[best], dist[best], closest[best], region[best], stuck[best]


def _chunk(ref: ReferenceSurface, p: FloatArray) -> Closest:
    n = len(p)
    _, seeds = ref.centroid_tree.query(p, k=min(SEEDS, len(ref.faces)), workers=-1)
    seeds = np.asarray(seeds).reshape(n, -1)
    _, nearest_vertex = ref.vertex_tree.query(p, k=1, workers=-1)
    ring_owner, ring = _ring_of(ref, np.asarray(nearest_vertex))
    owner = np.concatenate([np.repeat(np.arange(n), seeds.shape[1]), ring_owner])
    tri, dist, closest, region, stuck = _best_from_seeds(
        ref, p, owner, np.concatenate([seeds.ravel(), ring])
    )

    if len(ref.edge_vertices):
        edge_dist, nearest_edge = ref.edge_vertex_tree.query(p, k=1, workers=-1)
        near = np.flatnonzero(edge_dist <= 3.0 * dist + EDGE_BAND_MM)
        if len(near):
            ring_owner, ring = _ring_of(ref, ref.edge_vertices[nearest_edge[near]])
            t2, d2, c2, r2, s2 = _best_from_seeds(ref, p[near], ring_owner, ring)
            better = d2 < dist[near]
            rows = near[better]
            tri[rows], dist[rows], closest[rows] = t2[better], d2[better], c2[better]
            region[rows], stuck[rows] = r2[better], s2[better]

    # Pseudo-normal of the feature (face interior, edge, vertex) holding the closest point.
    normal = ref.face_normals[tri].copy()
    vertex_local = np.select([region == VERT_A, region == VERT_B, region == VERT_C], [0, 1, 2], -1)
    is_vertex = vertex_local >= 0
    normal[is_vertex] = ref.vertex_normals[ref.faces[tri[is_vertex], vertex_local[is_vertex]]]
    edge_local = np.select([region == EDGE_AB, region == EDGE_BC, region == EDGE_CA], [0, 1, 2], -1)
    is_edge = edge_local >= 0
    normal[is_edge] = ref.edge_normals[ref.faces_unique_edges[tri[is_edge], edge_local[is_edge]]]
    sign = np.where(_dot(p - closest, normal) >= 0, 1.0, -1.0)
    return Closest(signed=sign * dist, triangle=tri, converged=~stuck)


def closest_points(
    ref: ReferenceSurface, points: FloatArray, job: JobContext | None = None
) -> Closest:
    """Signed distance of every point to the reference surface, in chunks."""
    points = np.ascontiguousarray(points, dtype=np.float64)
    signed = np.empty(len(points))
    triangle = np.empty(len(points), dtype=np.int64)
    converged = np.empty(len(points), dtype=bool)
    for start in range(0, len(points), CHUNK):
        if job is not None:
            job.check_cancelled()
            job.progress(start / max(len(points), 1), ProgressStage.COMPARING)
        part = _chunk(ref, points[start : start + CHUNK])
        end = start + len(part.signed)
        signed[start:end], triangle[start:end] = part.signed, part.triangle
        converged[start:end] = part.converged
    return Closest(signed=signed, triangle=triangle, converged=converged)
