"""Planar and rotational sections of the scan in an explicit plane frame.

The frame fixes the sketch coordinates: constraints such as "horizontal" and the
stored entities refer to it, so it never depends on the order of mesh data.
A rotational frame has its X direction along the axis and its Y direction
radial; the half-plane v >= 0 carries the profile.
"""

from __future__ import annotations

from dataclasses import dataclass

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

MAX_SUPPORT_POINTS = 60_000
"""Scan vertices used to fit a section (evenly strided above this count)."""
BAND_HALF_WIDTH = 2.0
"""Planar sections also fit to vertices this close to the cut (mm)..."""
BAND_MAX_TILT = np.sin(np.radians(10.0))
"""...on walls perpendicular to the plane: |vertex normal . plane normal| below this."""


@dataclass(frozen=True)
class Section:
    """Section polylines in plane coordinates (u, v), and the scan points to fit them to.

    A single cut carries the noise of one row of scan vertices. `support` adds more
    rows: for rotational sections every vertex, folded into the half-plane as
    (distance along the axis, distance from the axis), which averages the whole
    circumference; for planar sections the vertices of walls perpendicular to the
    plane within 2 mm of the cut, projected onto it (they lie on the section curve).
    """

    loops: list[FloatArray]
    chains: list[FloatArray]
    support: FloatArray | None = None
    rotational: bool = False

    @property
    def empty(self) -> bool:
        return not self.loops and not self.chains

    def raw_points(self) -> FloatArray:
        parts = [*self.loops, *self.chains]
        return np.vstack(parts) if parts else np.zeros((0, 2))


def unit3(vector: npt.ArrayLike) -> FloatArray:
    v = np.asarray(vector, dtype=np.float64).reshape(3)
    return v / np.linalg.norm(v)


def in_plane_direction(normal: FloatArray, hint: npt.ArrayLike | None) -> FloatArray:
    """`hint` (default global X, then Y) projected into the plane with this normal."""
    candidates = [hint] if hint is not None else []
    candidates += [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    for candidate in candidates:
        c = np.asarray(candidate, dtype=np.float64)
        projected = c - float(c @ normal) * normal
        if np.linalg.norm(projected) > 1e-6:
            return projected / np.linalg.norm(projected)
    raise ValueError("no in-plane direction")


def standard_frame(name: str) -> PlaneFrame:
    x, y = (np.asarray(v, dtype=np.float64) for v in STANDARD_FRAMES[name])
    return PlaneFrame(np.zeros(3), x, np.cross(x, y))


def plane_frame(
    origin: npt.ArrayLike,
    normal: npt.ArrayLike,
    offset: float,
    x_direction: npt.ArrayLike | None,
    flip: bool,
    default_x: npt.ArrayLike | None = None,
) -> PlaneFrame:
    """A sketch frame: moved `offset` along the normal, X from the hint, optionally flipped."""
    n = unit3(normal)
    x = in_plane_direction(n, x_direction if x_direction is not None else default_x)
    o = np.asarray(origin, dtype=np.float64) + offset * n
    return PlaneFrame(o, x, -n if flip else n)


def nearest_axis_point(point: npt.ArrayLike, direction: FloatArray) -> FloatArray:
    """The point of an axis closest to the global origin."""
    p = np.asarray(point, dtype=np.float64)
    result: FloatArray = p - float(p @ direction) * direction
    return result


def rotational_frame(
    point: npt.ArrayLike, direction: npt.ArrayLike, angle_deg: float
) -> PlaneFrame:
    """Half-plane frame: X along the axis, Y radial at `angle_deg` from global Z (or X)."""
    axis = unit3(direction)
    radial = in_plane_direction(axis, (0.0, 0.0, 1.0))
    angle = np.radians(angle_deg)
    radial = np.cos(angle) * radial + np.sin(angle) * np.cross(axis, radial)
    origin = nearest_axis_point(point, axis)
    return PlaneFrame(origin, axis, np.cross(axis, radial))


def to_uv(frame: PlaneFrame, xyz: npt.ArrayLike) -> FloatArray:
    d = np.asarray(xyz, dtype=np.float64) - frame.origin
    return np.column_stack([d @ frame.x_dir, d @ frame.y_dir])


def to_xyz(frame: PlaneFrame, uv: npt.ArrayLike) -> FloatArray:
    p = np.atleast_2d(np.asarray(uv, dtype=np.float64))
    result: FloatArray = frame.origin + p[:, :1] * frame.x_dir + p[:, 1:2] * frame.y_dir
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
    # The vertex alone on its side of the plane is the apex; the plane cuts its two edges.
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
    """Polylines through segments that share end points: (points, closed)."""
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
    order = np.argsort(labels, kind="stable")
    bounds = np.flatnonzero(np.diff(labels[order])) + 1
    polylines: list[tuple[FloatArray, bool]] = []
    visited = np.zeros(count, dtype=bool)
    for members in np.split(order, bounds):
        degree = np.array([len(neighbours[m]) for m in members])
        endpoints = members[degree == 1]
        start = int(endpoints[0]) if len(endpoints) else int(members[0])
        path = [start]
        visited[start] = True
        previous, current = -1, start
        while True:
            options = [m for m in neighbours[current] if m != previous and not visited[m]]
            if not options:
                break
            previous, current = current, options[0]
            visited[current] = True
            path.append(current)
        closed = len(endpoints) == 0 and len(path) > 2 and start in neighbours[current]
        polylines.append((position[path], closed))
    return polylines


def planar_section(
    vertices: FloatArray,
    faces: IntArray,
    frame: PlaneFrame,
    offset: float = 0.0,
    normals: FloatArray | None = None,
    min_points: int = 8,
) -> Section:
    """Closed loops and open chains cut `offset` mm along the normal, in (u, v) of `frame`.

    With vertex `normals`, the section also carries the support points of the band
    around the cut (see `Section`).
    """
    origin = frame.origin + offset * frame.normal
    loops: list[FloatArray] = []
    chains: list[FloatArray] = []
    for points, closed in chain_segments(plane_segments(vertices, faces, origin, frame.normal)):
        if len(points) >= min_points:
            (loops if closed else chains).append(to_uv(frame, points))
    support = None
    if normals is not None and (loops or chains):
        near = np.abs((vertices - origin) @ frame.normal) <= BAND_HALF_WIDTH
        upright = np.abs(normals @ frame.normal) <= BAND_MAX_TILT
        chosen = vertices[near & upright]
        stride = max(1, len(chosen) // MAX_SUPPORT_POINTS)
        support = to_uv(frame, chosen[::stride])
    return Section(loops, chains, support)


def fold(frame: PlaneFrame, vertices: FloatArray) -> FloatArray:
    """(distance along the axis, distance from the axis) of points; the axis is frame X."""
    d = vertices - frame.origin
    h = d @ frame.x_dir
    rho = np.sqrt(np.maximum(np.einsum("ij,ij->i", d, d) - h * h, 0.0))
    return np.column_stack([h, rho])


def rotational_section(
    vertices: FloatArray, faces: IntArray, frame: PlaneFrame, min_points: int = 8
) -> Section:
    """The profile in the half-plane v >= 0 of a rotational frame.

    The cut through the axis gives the order of the profile (the polylines); the
    scan vertices of every angle, folded into the half-plane, are the points the
    entities are fitted to.
    """
    cut = planar_section(vertices, faces, frame, 0.0, min_points=2)
    loops: list[FloatArray] = []
    chains: list[FloatArray] = []
    for points, closed in [(p, True) for p in cut.loops] + [(p, False) for p in cut.chains]:
        keep = points[:, 1] >= 0.0
        if keep.all():
            if len(points) >= min_points:
                (loops if closed else chains).append(points)
            continue
        if closed:
            shift = int(np.argmin(keep))
            points, keep = np.roll(points, -shift, axis=0), np.roll(keep, -shift)
        runs = np.split(np.arange(len(points)), np.flatnonzero(np.diff(keep.astype(np.int8))) + 1)
        for run in runs:
            if keep[run[0]] and len(run) >= min_points:
                chains.append(_to_axis(points, run, closed))
    stride = max(1, len(vertices) // MAX_SUPPORT_POINTS)
    return Section(loops, chains, fold(frame, vertices[::stride]), rotational=True)


def _to_axis(points: FloatArray, run: npt.NDArray[np.int64], closed: bool) -> FloatArray:
    """A run of points with v >= 0, extended to where its polyline crosses the axis."""
    pieces = [points[run]]
    n = len(points)
    for inside, outside, where in ((run[0], run[0] - 1, 0), (run[-1], run[-1] + 1, 1)):
        if closed:
            outside %= n
        if 0 <= outside < n:
            a, b = points[inside], points[outside]
            t = a[1] / (a[1] - b[1])
            crossing = (a + t * (b - a))[None, :]
            crossing[0, 1] = 0.0
            pieces.insert(0 if where == 0 else len(pieces), crossing)
    return np.vstack(pieces)
