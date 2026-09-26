"""Signed closest-point distances from scan points to a reference surface.

Seeded vertex-ring descent with one walker per (point, B-Rep face), a second pass
from B-Rep edge vertices, and the pseudo-normal sign (Baerentzen and Aanaes).
Details and measurements: `.work/research/algorithms-cad.md` section 4.2.

A walker evaluates its triangle; while the closest point lies on a triangle edge
or vertex, it moves to the best triangle around the vertices of that edge or
vertex. Those triangles are exactly the ones that touch the closest point, so a
walker that cannot improve has found a local minimum of the distance.
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
type BoolArray = npt.NDArray[np.bool_]

# Region codes of the closest point on a triangle.
INTERIOR, VERT_A, VERT_B, VERT_C, EDGE_AB, EDGE_BC, EDGE_CA = range(7)

# Triangle corners (local indices) that touch the closest point, per region code; -1 = none.
_TOUCHING = np.array(
    [[-1, -1], [0, -1], [1, -1], [2, -1], [0, 1], [1, 2], [2, 0]],
    dtype=np.int64,
)
# Local edge index (AB = 0, BC = 1, CA = 2) per region code, for the edge pseudo-normal.
_EDGE_OF_REGION = np.array([-1, -1, -1, -1, 0, 1, 2], dtype=np.int64)

SEEDS = 8
MAX_WALK = 48
EDGE_BAND_MM = 1.0
CHUNK = 200_000


@dataclass(frozen=True)
class Closest:
    """Per point: signed distance (positive outside), reference triangle and convergence."""

    signed: FloatArray
    triangle: IntArray
    converged: BoolArray


def _dot(u: FloatArray, v: FloatArray) -> FloatArray:
    result: FloatArray = np.einsum("ij,ij->i", u, v)
    return result


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

    with np.errstate(divide="ignore", invalid="ignore"):
        denom = va + vb + vc
        denom = np.where(np.abs(denom) < 1e-300, 1e-300, denom)
        t_ab = d1 / (d1 - d3)
        t_ca = d2 / (d2 - d6)
        t_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        # Ericson's tests in his order; np.select takes the first that holds.
        tests = [
            (d1 <= 0) & (d2 <= 0),
            (d3 >= 0) & (d4 <= d3),
            (vc <= 0) & (d1 >= 0) & (d3 <= 0),
            (d6 >= 0) & (d5 <= d6),
            (vb <= 0) & (d2 >= 0) & (d6 <= 0),
            (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0),
        ]
        zero, one = np.zeros_like(d1), np.ones_like(d1)
        v = np.select(tests, [zero, one, t_ab, zero, zero, 1 - t_bc], vb / denom)
        w = np.select(tests, [zero, zero, zero, one, t_ca, t_bc], vc / denom)
    codes = [VERT_A, VERT_B, EDGE_AB, VERT_C, EDGE_CA, EDGE_BC]
    region = np.select(tests, codes, INTERIOR).astype(np.int64)
    closest = a + v[:, None] * ab + w[:, None] * ac
    return closest, region


def _first_per_owner(owner: IntArray, dist: FloatArray) -> IntArray:
    """Index of the smallest distance per owner; owners must be non-decreasing."""
    starts = np.flatnonzero(np.r_[True, owner[1:] != owner[:-1]])
    counts = np.diff(np.r_[starts, len(owner)])
    smallest = np.minimum.reduceat(dist, starts)
    hits = np.flatnonzero(dist == np.repeat(smallest, counts))
    first = np.r_[True, owner[hits][1:] != owner[hits][:-1]]
    result: IntArray = hits[first]
    return result


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
    """All triangles around each vertex, as (row, triangle) pairs with rows in order."""
    lengths = np.diff(ref.vf_offsets)[vertices]
    starts = ref.vf_offsets[vertices]
    total = int(lengths.sum())
    position = (
        np.arange(total)
        - np.repeat(np.cumsum(lengths) - lengths, lengths)
        + np.repeat(starts, lengths)
    )
    return np.repeat(np.arange(len(vertices)), lengths), ref.vf_faces[position]


def _touching(
    ref: ReferenceSurface, triangles: IntArray, region: IntArray
) -> tuple[IntArray, IntArray]:
    """Triangles around the vertex or edge holding each closest point, as (row, triangle)."""
    corners = _TOUCHING[region]
    rows = np.repeat(np.arange(len(triangles)), 2)
    local = corners.ravel()
    valid = local >= 0
    rows, local = rows[valid], local[valid]
    owner, ring = _ring_of(ref, ref.faces[triangles[rows], local])
    return rows[owner], ring


def _walk(
    ref: ReferenceSurface, p: FloatArray, tri: IntArray
) -> tuple[IntArray, FloatArray, FloatArray, IntArray, BoolArray]:
    """Greedy descent until the closest point is interior or no neighbour improves it."""
    tri, dist, closest, region = _closest_among(ref, p, np.arange(len(p)), tri)
    active = np.flatnonzero(region != INTERIOR)
    for _ in range(MAX_WALK):
        if len(active) == 0:
            break
        ring_owner, ring = _touching(ref, tri[active], region[active])
        t2, d2, c2, r2 = _closest_among(ref, p[active], ring_owner, ring)
        moved = (t2 != tri[active]) & (d2 < dist[active] - 1e-12)
        rows = active[moved]
        tri[rows], dist[rows], closest[rows], region[rows] = (
            t2[moved],
            d2[moved],
            c2[moved],
            r2[moved],
        )
        active = rows[r2[moved] != INTERIOR]
    stuck = np.zeros(len(p), dtype=bool)
    stuck[active] = True
    return tri, dist, closest, region, stuck


def _best_from_seeds(
    ref: ReferenceSurface, p: FloatArray, owner: IntArray, seed: IntArray
) -> tuple[IntArray, FloatArray, FloatArray, IntArray, BoolArray]:
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
    seeds = np.asarray(seeds, dtype=np.int64).reshape(n, -1)
    _, nearest_vertex = ref.vertex_tree.query(p, k=1, workers=-1)
    ring_owner, ring = _ring_of(ref, np.asarray(nearest_vertex, dtype=np.int64))
    owner = np.concatenate([np.repeat(np.arange(n), seeds.shape[1]), ring_owner])
    candidates = np.concatenate([seeds.ravel(), ring])
    tri, dist, closest, region, stuck = _best_from_seeds(ref, p, owner, candidates)

    # Next to a convex edge a point inside the material has a local minimum on each
    # adjacent face; seeds from one face never find the other, so walk from the edge too.
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
    edge_local = _EDGE_OF_REGION[region]
    is_edge = edge_local >= 0
    normal[is_edge] = ref.edge_normals[ref.faces_unique_edges[tri[is_edge], edge_local[is_edge]]]
    sign = np.where(_dot(p - closest, normal) >= 0, 1.0, -1.0)
    return Closest(signed=sign * dist, triangle=tri, converged=~stuck)


def closest_points(
    ref: ReferenceSurface, points: FloatArray, job: JobContext | None = None
) -> Closest:
    """Signed distance of every point to the reference surface, in cancellable chunks."""
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
