"""Closed contours in a plane frame: cuts through triangles, boundary loops, areas, insides."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


def section_loops(uvh: FloatArray, faces: IntArray, at: float) -> list[FloatArray]:
    """Closed loops (u, v) where the plane h = `at` cuts the triangles.

    Each cut triangle gives a segment between two of its edges; segments sharing an
    edge are joined. Loops that run open (out of the triangle set) are left out.
    """
    above = uvh[faces, 2] >= at
    cut = above.sum(axis=1) % 3 != 0
    faces, above = faces[cut], above[cut]
    if len(faces) == 0:
        return []
    following = np.roll(faces, -1, axis=1)
    # Edge k runs from corner k to corner k + 1; exactly two edges of a cut triangle cross.
    crossing = above != np.roll(above, -1, axis=1)
    rows, columns = np.nonzero(crossing)
    ends = np.sort(np.column_stack([faces[rows, columns], following[rows, columns]]), axis=1)
    edges, point_of = np.unique(ends, axis=0, return_inverse=True)
    segments = point_of.reshape(-1, 2)
    low, high = uvh[edges[:, 0]], uvh[edges[:, 1]]
    t = (at - low[:, 2]) / (high[:, 2] - low[:, 2])
    points = low[:, :2] + t[:, None] * (high[:, :2] - low[:, :2])

    neighbours: list[list[int]] = [[] for _ in range(len(points))]
    for a, b in segments.tolist():
        neighbours[a].append(b)
        neighbours[b].append(a)
    used = np.zeros(len(points), dtype=bool)
    loops: list[FloatArray] = []
    for start in range(len(points)):
        if used[start] or len(neighbours[start]) != 2:
            continue
        loop = [start]
        used[start] = True
        previous, current = start, neighbours[start][0]
        while current != start and not used[current] and len(neighbours[current]) == 2:
            used[current] = True
            loop.append(current)
            first, second = neighbours[current]
            previous, current = current, second if first == previous else first
        if current == start and len(loop) >= 3:
            loops.append(points[loop])
    return loops


def boundary_loops(faces: IntArray) -> list[IntArray]:
    """Closed loops of the boundary edges of a triangle set (vertex indices, in order)."""
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    keys = np.sort(edges, axis=1)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    boundary = edges[counts[inverse.ravel()] == 1]
    following: dict[int, int] = {}
    for a, b in boundary.tolist():
        following.setdefault(a, b)
    loops: list[IntArray] = []
    seen: set[int] = set()
    for start in list(following):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        current = following.get(start)
        while current is not None and current != start and current not in seen:
            loop.append(current)
            seen.add(current)
            current = following.get(current)
        if current == start and len(loop) >= 3:
            loops.append(np.asarray(loop, dtype=np.int64))
    return loops


def signed_area(points: FloatArray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1)))


def inside_contour(points: FloatArray, contour: FloatArray) -> BoolArray:
    """Point-in-polygon by the even-odd rule (vectorised over the polygon edges)."""
    inside = np.zeros(len(points), dtype=bool)
    low, high = contour.min(axis=0), contour.max(axis=0)
    box = np.flatnonzero(np.all((points >= low) & (points <= high), axis=1))
    x, y = points[box, 0], points[box, 1]
    hits = np.zeros(len(box), dtype=bool)
    a = contour
    b = np.roll(contour, -1, axis=0)
    for (ax, ay), (bx, by) in zip(a, b, strict=True):
        crosses = (ay > y) != (by > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = ax + (y - ay) * (bx - ax) / (by - ay)
        hits ^= crosses & (x < at)
    inside[box] = hits
    return inside
