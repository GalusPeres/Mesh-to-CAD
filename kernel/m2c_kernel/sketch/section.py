"""Planar and rotational sections of the scan in an explicit plane frame."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from m2c_kernel.document.results import PlaneFrame

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

STANDARD_FRAMES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
}
"""In-plane X and Y direction of the standard planes; the normal is X x Y."""


def frame_from_normal(
    origin: npt.ArrayLike, normal: npt.ArrayLike, x_hint: npt.ArrayLike | None = None
) -> PlaneFrame:
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    hint = np.asarray(x_hint if x_hint is not None else (1.0, 0.0, 0.0), dtype=np.float64)
    x = hint - float(hint @ n) * n
    if np.linalg.norm(x) < 1e-6:
        x = np.cross(n, [0.0, 1.0, 0.0] if abs(n[1]) < 0.9 else [1.0, 0.0, 0.0])
    return PlaneFrame(np.asarray(origin, dtype=np.float64), x / np.linalg.norm(x), n)


def standard_frame(name: str) -> PlaneFrame:
    x, y = (np.asarray(v, dtype=np.float64) for v in STANDARD_FRAMES[name])
    return PlaneFrame(np.zeros(3), x, np.cross(x, y))


def adjust_frame(
    frame: PlaneFrame, offset: float, x_direction: npt.ArrayLike | None, flip: bool
) -> PlaneFrame:
    """Offset along the normal, optional in-plane X direction, optional flip (mirrors Y)."""
    moved = frame_from_normal(
        frame.origin + offset * frame.normal,
        frame.normal,
        x_direction if x_direction is not None else frame.x_dir,
    )
    if flip:
        return PlaneFrame(moved.origin, moved.x_dir, -moved.normal)
    return moved


def to_uv(frame: PlaneFrame, xyz: FloatArray) -> FloatArray:
    d = np.asarray(xyz) - frame.origin
    return np.column_stack([d @ frame.x_dir, d @ frame.y_dir])


def to_xyz(frame: PlaneFrame, uv: FloatArray) -> FloatArray:
    uv = np.atleast_2d(uv)
    result: FloatArray = frame.origin + uv[:, :1] * frame.x_dir + uv[:, 1:2] * frame.y_dir
    return result


def plane_segments(
    vertices: FloatArray, faces: IntArray, origin: FloatArray, normal: FloatArray
) -> FloatArray:
    """Intersection segments (m, 2, 3) of the triangles with the plane."""
    dist = (vertices - origin) @ normal
    d = dist[faces]
    above = d > 0
    count = above.sum(axis=1)
    crossing = (count == 1) | (count == 2)
    tri = faces[crossing]
    d = d[crossing]
    above = above[crossing]
    # the vertex alone on its side is the apex; the plane cuts its two edges
    lonely = np.where(above.sum(axis=1) == 1, np.argmax(above, axis=1), np.argmin(above, axis=1))
    rows = np.arange(len(tri))
    apex = tri[rows, lonely]
    b = tri[rows, (lonely + 1) % 3]
    c = tri[rows, (lonely + 2) % 3]
    da, db, dc = d[rows, lonely], d[rows, (lonely + 1) % 3], d[rows, (lonely + 2) % 3]
    pa = vertices[apex]
    p1 = pa + (vertices[b] - pa) * (da / (da - db))[:, None]
    p2 = pa + (vertices[c] - pa) * (da / (da - dc))[:, None]
    result: FloatArray = np.stack([p1, p2], axis=1)
    return result


def chain_segments(segments: FloatArray, merge: float = 1e-7) -> list[tuple[FloatArray, bool]]:
    """Polylines through segments that share endpoints: (points, closed)."""
    if len(segments) == 0:
        return []
    ends = segments.reshape(-1, 3)
    scale = max(float(np.ptp(ends, axis=0).max()), 1.0)
    keys = np.round(ends / (merge * scale)).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    count = int(inverse.max()) + 1
    position = np.zeros((count, 3))
    position[inverse] = ends
    node = inverse.reshape(-1, 2)
    node = node[node[:, 0] != node[:, 1]]
    neighbours: list[list[int]] = [[] for _ in range(count)]
    for a, b in node:
        neighbours[a].append(int(b))
        neighbours[b].append(int(a))
    graph = coo_matrix((np.ones(len(node)), (node[:, 0], node[:, 1])), shape=(count, count))
    _, labels = connected_components(graph, directed=False)
    polylines: list[tuple[FloatArray, bool]] = []
    visited = np.zeros(count, dtype=bool)
    for component in np.unique(labels):
        members = np.flatnonzero(labels == component)
        degree = np.array([len(neighbours[m]) for m in members])
        endpoints = members[degree == 1]
        start = int(endpoints[0]) if len(endpoints) else int(members[0])
        path = [start]
        visited[start] = True
        previous = -1
        current = start
        closed = False
        while True:
            options = [m for m in neighbours[current] if m != previous and not visited[m]]
            if not options:
                closed = len(endpoints) == 0 and start in neighbours[current] and len(path) > 2
                break
            previous, current = current, options[0]
            visited[current] = True
            path.append(current)
        polylines.append((position[path], closed))
    return polylines


def planar_section(
    vertices: FloatArray,
    faces: IntArray,
    frame: PlaneFrame,
    offset: float,
    min_points: int = 8,
) -> tuple[list[FloatArray], list[FloatArray]]:
    """Closed loops and open chains in (u, v) of `frame`, cut `offset` mm along its normal."""
    origin = frame.origin + offset * frame.normal
    polylines = chain_segments(plane_segments(vertices, faces, origin, frame.normal))
    loops: list[FloatArray] = []
    chains: list[FloatArray] = []
    for points, closed in polylines:
        if len(points) < min_points:
            continue
        (loops if closed else chains).append(to_uv(frame, points))
    return loops, chains


def rotational_frame(
    point: npt.ArrayLike, direction: npt.ArrayLike, x_hint: npt.ArrayLike | None
) -> PlaneFrame:
    """Half-plane frame: u along the axis, v radial (v >= 0 is the section side)."""
    axis = np.asarray(direction, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    hint = np.asarray(x_hint if x_hint is not None else (0.0, 0.0, 1.0), dtype=np.float64)
    radial = hint - float(hint @ axis) * axis
    if np.linalg.norm(radial) < 1e-6:
        radial = np.cross(axis, [0.0, 1.0, 0.0] if abs(axis[1]) < 0.9 else [1.0, 0.0, 0.0])
    radial = radial / np.linalg.norm(radial)
    return PlaneFrame(np.asarray(point, dtype=np.float64), axis, np.cross(axis, radial))


def rotational_section(
    vertices: FloatArray, faces: IntArray, frame: PlaneFrame, min_points: int = 8
) -> tuple[list[FloatArray], list[FloatArray]]:
    """The profile in the half-plane v >= 0 through the axis (frame X = axis)."""
    loops, chains = planar_section(vertices, faces, frame, 0.0, min_points=2)
    pieces: list[FloatArray] = []
    closed_pieces: list[FloatArray] = []
    for points, closed in [(p, True) for p in loops] + [(p, False) for p in chains]:
        keep = points[:, 1] >= 0.0
        if keep.all():
            (closed_pieces if closed else pieces).append(points)
            continue
        if closed:
            shift = int(np.argmin(keep))
            points, keep = np.roll(points, -shift, axis=0), np.roll(keep, -shift)
        runs = np.split(np.arange(len(points)), np.flatnonzero(np.diff(keep.astype(np.int8))) + 1)
        for run in runs:
            if keep[run[0]] and len(run) >= min_points:
                segment = points[run]
                segment[:, 1] = np.maximum(segment[:, 1], 0.0)
                pieces.append(segment)
    return [p for p in closed_pieces if len(p) >= min_points], pieces
