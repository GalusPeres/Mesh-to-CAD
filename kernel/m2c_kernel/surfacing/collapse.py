"""Manifold-preserving quadric edge collapse for the last reduction step of the cage.

fast_simplification reduces large scans quickly, but at a few hundred to a thousand
triangles it folds thin parts (the Armadillo's fingers and ears) into edges with
three or four faces. The cage is therefore reduced by fast_simplification only to an
intermediate size, where its result is still manifold, and from there to the target
by this collapse, which keeps the surface a 2-manifold:

- Quadric error metric (Garland-Heckbert) with the optimal vertex position; boundary
  edges add a perpendicular plane so open borders keep their course.
- The link condition: the two end vertices may share no neighbours other than the
  apexes of the edge's faces, so no edge or vertex becomes non-manifold.
- An interior edge between two boundary vertices is never collapsed (it would pinch
  the surface), and no vertex drops below three (interior) or two (boundary) edges.
- The collapse is rejected when a surrounding triangle turns by more than about 80
  degrees or degenerates to a sliver.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]

BOUNDARY_WEIGHT = 10.0
"""Weight of the perpendicular boundary planes relative to the face planes."""
MIN_NORMAL_COSINE = 0.2
"""A surrounding triangle may turn by at most arccos(0.2) = 78 degrees."""
MIN_QUALITY = 0.05
"""Smallest triangle quality 4 sqrt(3) area / sum of squared sides (1 = equilateral)."""
CANCEL_INTERVAL = 256


def _plane_quadrics(normals: FloatArray, points: FloatArray, weights: FloatArray) -> FloatArray:
    """Weighted outer products of the planes (n, -n . p) as (k, 4, 4) matrices."""
    planes = np.concatenate([normals, -np.einsum("ij,ij->i", normals, points)[:, None]], axis=1)
    quadrics: FloatArray = weights[:, None, None] * planes[:, :, None] * planes[:, None, :]
    return quadrics


class _Collapser:
    def __init__(self, vertices: FloatArray, faces: IntArray) -> None:
        self.pos = np.array(vertices, dtype=np.float64)
        self.faces = np.array(faces, dtype=np.int64)
        n_vertices = len(self.pos)
        self.face_alive = np.ones(len(self.faces), dtype=bool)
        self.alive_faces = len(self.faces)
        self.vertex_faces: list[set[int]] = [set() for _ in range(n_vertices)]
        for index, face in enumerate(self.faces.tolist()):
            for vertex in face:
                self.vertex_faces[vertex].add(index)
        self.version = np.zeros(n_vertices, dtype=np.int64)
        self.boundary = np.zeros(n_vertices, dtype=bool)
        self.quadric = np.zeros((n_vertices, 4, 4))
        self._initial_quadrics()
        self.heap: list[tuple[float, int, int, int, int, float, float, float]] = []

    def _initial_quadrics(self) -> None:
        corners = self.pos[self.faces]
        cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        doubled_area = np.linalg.norm(cross, axis=1)
        normals = cross / np.maximum(doubled_area, 1e-300)[:, None]
        face_quadrics = _plane_quadrics(normals, corners[:, 0], 0.5 * doubled_area)
        for slot in range(3):
            np.add.at(self.quadric, self.faces[:, slot], face_quadrics)

        start = self.faces.ravel()
        end = np.roll(self.faces, -1, axis=1).ravel()
        keys = np.minimum(start, end) * len(self.pos) + np.maximum(start, end)
        _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
        on_boundary = counts[inverse] == 1
        if not np.any(on_boundary):
            return
        a, b = start[on_boundary], end[on_boundary]
        face_normals = np.repeat(normals, 3, axis=0)[on_boundary]
        direction = self.pos[b] - self.pos[a]
        length_sq = np.einsum("ij,ij->i", direction, direction)
        perpendicular = np.cross(direction, face_normals)
        perpendicular /= np.maximum(np.linalg.norm(perpendicular, axis=1), 1e-300)[:, None]
        edge_quadrics = _plane_quadrics(perpendicular, self.pos[a], BOUNDARY_WEIGHT * length_sq)
        np.add.at(self.quadric, a, edge_quadrics)
        np.add.at(self.quadric, b, edge_quadrics)
        self.boundary[a] = True
        self.boundary[b] = True

    def neighbours(self, vertex: int) -> set[int]:
        result: set[int] = set()
        for face in self.vertex_faces[vertex]:
            result.update(self.faces[face].tolist())
        result.discard(vertex)
        return result

    def push_edges(self, u: int, others: list[int]) -> None:
        """Compute the optimal position and cost of edges (u, w) and queue them."""
        if not others:
            return
        w = np.asarray(others, dtype=np.int64)
        quadric = self.quadric[u][None] + self.quadric[w]
        a, rhs = quadric[:, :3, :3], -quadric[:, :3, 3]
        determinant = np.linalg.det(a)
        scale = np.einsum("kii->k", a) ** 3
        solvable = np.abs(determinant) > 1e-10 * np.maximum(scale, 1e-300)
        candidates = np.stack(
            [
                np.broadcast_to(self.pos[u], (len(w), 3)),
                self.pos[w],
                0.5 * (self.pos[u] + self.pos[w]),
            ],
            axis=1,
        )
        if np.any(solvable):
            optimal = np.linalg.solve(a[solvable], rhs[solvable][:, :, None])[:, :, 0]
            candidates = np.concatenate([candidates, candidates[:, :1]], axis=1)
            candidates[solvable, 3] = optimal
        homogeneous = np.concatenate([candidates, np.ones((*candidates.shape[:2], 1))], axis=2)
        costs = np.einsum("kci,kij,kcj->kc", homogeneous, quadric, homogeneous)
        best = np.argmin(costs, axis=1)
        rows = np.arange(len(w))
        points = candidates[rows, best]
        for other, cost, point in zip(
            w.tolist(), costs[rows, best].tolist(), points.tolist(), strict=True
        ):
            heapq.heappush(
                self.heap,
                (
                    max(cost, 0.0),
                    u,
                    other,
                    int(self.version[u]),
                    int(self.version[other]),
                    point[0],
                    point[1],
                    point[2],
                ),
            )

    def valence(self, vertex: int) -> int:
        return len(self.neighbours(vertex))

    def can_collapse(self, u: int, v: int, point: FloatArray) -> bool:
        shared = self.vertex_faces[u] & self.vertex_faces[v]
        if not shared or len(shared) > 2:
            return False
        if len(shared) == 2 and self.boundary[u] and self.boundary[v]:
            return False
        apexes = {int(x) for face in shared for x in self.faces[face].tolist()} - {u, v}
        if self.neighbours(u) & self.neighbours(v) != apexes:
            return False
        for apex in apexes:
            if self.valence(apex) <= (2 if self.boundary[apex] else 3):
                return False
        merged_valence = self.valence(u) + self.valence(v) - 2 - len(shared)
        if merged_valence < (2 if self.boundary[u] or self.boundary[v] else 3):
            return False
        moved = (self.vertex_faces[u] | self.vertex_faces[v]) - shared
        if not moved:
            return False
        indices = np.fromiter(moved, dtype=np.int64)
        corners = self.pos[self.faces[indices]]
        before = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        replaced = (self.faces[indices] == u) | (self.faces[indices] == v)
        corners[replaced] = point
        after = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        before_len = np.linalg.norm(before, axis=1)
        after_len = np.linalg.norm(after, axis=1)
        cosine = np.einsum("ij,ij->i", before, after) / np.maximum(before_len * after_len, 1e-300)
        if np.any(cosine < MIN_NORMAL_COSINE):
            return False
        sides = corners - np.roll(corners, -1, axis=1)
        side_sq = np.einsum("kij,kij->k", sides, sides)
        quality = 2.0 * np.sqrt(3.0) * after_len / np.maximum(side_sq, 1e-300)
        return not bool(np.any(quality < MIN_QUALITY))

    def collapse(self, u: int, v: int, point: FloatArray) -> None:
        shared = self.vertex_faces[u] & self.vertex_faces[v]
        for face in shared:
            self.face_alive[face] = False
            for vertex in self.faces[face].tolist():
                self.vertex_faces[vertex].discard(face)
        self.alive_faces -= len(shared)
        for face in self.vertex_faces[v]:
            row = self.faces[face]
            row[row == v] = u
            self.vertex_faces[u].add(face)
        self.vertex_faces[v] = set()
        self.pos[u] = point
        self.quadric[u] += self.quadric[v]
        self.boundary[u] |= self.boundary[v]
        self.version[u] += 1
        self.version[v] += 1

    def result(self) -> tuple[FloatArray, IntArray]:
        faces = self.faces[self.face_alive]
        used = np.zeros(len(self.pos), dtype=bool)
        used[faces.ravel()] = True
        new_index = np.cumsum(used) - 1
        return self.pos[used], new_index[faces].astype(np.int64)


def collapse_to(
    vertices: FloatArray,
    faces: IntArray,
    target: int,
    check_cancelled: Callable[[], None] = lambda: None,
) -> tuple[FloatArray, IntArray]:
    """Reduce an oriented manifold triangle mesh to about `target` faces, keeping it manifold.

    Stops early when no admissible collapse is left, so the result may have more faces.
    """
    collapser = _Collapser(vertices, faces)
    if collapser.alive_faces <= target:
        return collapser.result()
    for u in range(len(collapser.pos)):
        higher = [w for w in collapser.neighbours(u) if w > u]
        collapser.push_edges(u, higher)
    steps = 0
    while collapser.heap and collapser.alive_faces > target:
        _, u, v, version_u, version_v, x, y, z = heapq.heappop(collapser.heap)
        if collapser.version[u] != version_u or collapser.version[v] != version_v:
            continue
        point = np.array([x, y, z])
        if not collapser.can_collapse(u, v, point):
            continue
        collapser.collapse(u, v, point)
        collapser.push_edges(u, sorted(collapser.neighbours(u)))
        steps += 1
        if steps % CANCEL_INTERVAL == 0:
            check_cancelled()
    return collapser.result()
