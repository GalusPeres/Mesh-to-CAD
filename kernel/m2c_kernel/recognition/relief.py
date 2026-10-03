"""Reliefs on a base plane: the raised and sunk features a designer would model.

In the plane's frame every vertex has a height h above the plane. Connected parts of
the scan that rise above it (bosses, buttons, ribs) or sink below it (pockets,
recesses, holes) are reliefs when they lie inside the plane's extent; the rest of the
part (side walls, the far side) is not.

For each relief:

- its level is the plane it stands on: the base plane, or the floor of the pocket
  that encloses it (a direction pad's arms stand in a round recess);
- its height (depth) is a high percentile of h above (below) that level;
- its contour is where a cut at half its height (depth) meets the scan, clear of
  rounded or chamfered feet, tops and mouths; the contour is fitted with a simple
  shape (`outline.py`);
- its top is flat when the upward triangles near the top lie on a plane parallel to
  the base; a pocket without a floor goes through the part (a through hole).

Cuts and areas, not vertex counts, carry the measurements: decimated scans and CAD
exports model a button's wall with triangles from foot to top and its top with a few
large ones, so a feature may have only a handful of vertices.

Raised and sunk parts are made of triangles (by their centre and their own normal),
not of vertices: on meshes with sharp edges a vertex normal blends both sides. Sunk
parts leave out the triangles facing away from the plane: they belong to the far
side of the part, and through holes would otherwise join it there. A pocket must open
at its plane (its rim reaches the plane), and its walls face inwards, towards its
axis; a boss's walls face outwards. Seen from the far side of a part, a boss's wall
would otherwise pass for a hole.

Inside each pocket the search repeats from the pocket floor, which finds features
that stand in the recess but do not reach above the base plane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.spatial import Delaunay

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.outline import Outline, fit_outline
from m2c_kernel.recognition.planes import BasePlane

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]

MIN_RISE_MM = 0.25
"""Smallest height (depth) of a relief; at least `RISE_NOISE` x the scan noise."""
RISE_NOISE = 8.0
MIN_VERTICES = 4
MIN_EXTENT_MM = 1.0
ON_PLANE_SHARE = 0.2
FAR_SIDE = 0.5
"""Sunk vertices whose normal points away from the plane beyond this cosine are left out."""
UP_FACING = 0.9
TOP_SHARE = 0.1
"""Less upward area near the top than this share of the outline: no top face (a dome,
or a pocket without a floor: a through hole)."""
WALL_FACING = 0.5
WALL_STEP_MM = 0.5
MIN_WALL_SHARE = 0.3
"""A designed feature has steep walls: at least this share of perimeter x height.
Gentle bulges of a curved or tilted surface have next to none (measured: buttons with
rounded edges 0.4 and more, holes about 1.1, bulges 0 to 0.22)."""
MIN_AREA_MM2 = 2.0
"""Smaller outlines are scan artefacts, not design features."""
MAX_SHARE = 0.4
"""A relief covers at most this share of its plane's extent."""
HEIGHT_PERCENTILE = 95.0
NORMAL_SMOOTHING_MM = 0.4
"""Vertex normals are averaged over neighbours about this far away."""
MAX_NORMAL_RINGS = 6
FLAT_TOP_FACTOR = 4.0
"""A top is flat when its points lie within this x the noise of a parallel plane."""


@dataclass(frozen=True)
class Relief:
    """A raised or sunk feature on a base plane.

    Attributes:
        kind: "boss" rises from its level, "pocket" sinks below it (a hole when
            `top` is "through").
        outline: Fitted contour shape in the plane's (u, v) frame.
        level: Height of the plane it stands on, above the base plane (mm).
        height: Height above (boss) or depth below (pocket) the level (mm).
        top: "flat" or "domed" (for pockets: the floor), "through" for a pocket
            without a floor.
        contour: (k, 2) measured contour in the plane frame.
        vertices: Scan vertices of the feature.
        parent: Index of the enclosing pocket, if any.
    """

    kind: Literal["boss", "pocket"]
    outline: Outline
    level: float
    height: float
    top: Literal["flat", "domed", "through"]
    contour: FloatArray
    vertices: IntArray
    parent: int | None = None
    children: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class _Context:
    plane: BasePlane
    uvh: FloatArray
    faces: IntArray
    graph: sp.csr_matrix
    noise: float
    threshold: float
    footprint: Delaunay
    extent_area: float
    on_plane: BoolArray
    """Vertices of the base plane's own triangles."""
    facing: FloatArray
    """Cosine between each vertex normal and the plane normal."""
    normals: FloatArray


@dataclass(frozen=True)
class MeshData:
    """What every plane's search needs of the mesh, computed once."""

    vertices: FloatArray
    faces: IntArray
    graph: sp.csr_matrix
    """Vertex adjacency."""
    normals: FloatArray
    """Smoothed unit vertex normals (`vertex_normals`)."""
    face_normals: FloatArray
    """(F, 2, 3) unit triangle normals: the triangle's own, and the mean of its smoothed
    corner normals (`face_normals`)."""


def mesh_data(vertices: FloatArray, faces: IntArray) -> MeshData:
    n = len(vertices)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    graph = sp.csr_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    graph = (graph + graph.T).tocsr()
    graph.data[:] = 1.0
    normals = vertex_normals(vertices, faces, graph)
    return MeshData(vertices, faces, graph, normals, face_normals(vertices, faces, normals))


def find_reliefs(data: MeshData, plane: BasePlane, noise: float) -> list[Relief]:
    """Raised and sunk features on the plane, pockets with the features inside them."""
    vertices, faces, graph = data.vertices, data.faces, data.graph
    uvh = plane.to_plane(vertices)
    inlier_vertices = np.unique(faces[plane.faces])
    hull_points = uvh[inlier_vertices, :2]
    footprint = Delaunay(hull_points)
    n = len(vertices)
    threshold = max(MIN_RISE_MM, RISE_NOISE * noise)
    span = np.ptp(hull_points, axis=0)
    on_plane = np.zeros(n, dtype=bool)
    on_plane[inlier_vertices] = True
    normals = data.normals
    facing = normals @ plane.normal
    context = _Context(
        plane,
        uvh,
        faces,
        graph,
        noise,
        threshold,
        footprint,
        float(span[0] * span[1]),
        on_plane,
        facing,
        normals,
    )

    reliefs: list[Relief] = []
    corners = uvh[faces]
    centre_h = corners[:, :, 2].mean(axis=1)
    # Far side: either normal of the triangle points away from the plane.
    away = (data.face_normals @ plane.normal).min(axis=1) < -FAR_SIDE
    sunk = (centre_h < -threshold) & ~away
    searches: tuple[tuple[Literal["boss", "pocket"], BoolArray], ...] = (
        ("boss", centre_h > threshold),
        ("pocket", sunk),
    )
    for kind, members in searches:
        for part in _parts(context, members):
            relief = _measure(context, part, kind, level=0.0)
            if relief is not None:
                reliefs.append(relief)

    # Features standing in a pocket are measured from its floor: the bosses found on
    # the base plane inside it are replaced by the parts rising from the floor, which
    # also finds those that do not reach above the base plane.
    pockets = [relief for relief in reliefs if relief.kind == "pocket"]
    reliefs = [relief for relief in reliefs if relief.kind == "boss"]
    result: list[Relief] = []
    face_centres = corners[:, :, :2].mean(axis=1)
    for pocket in pockets:
        floor = pocket.level - pocket.height
        inside = inside_contour(uvh[:, :2], pocket.contour)
        reliefs = [relief for relief in reliefs if not _covered(relief, inside)]
        claimed = np.zeros(n, dtype=bool)
        for relief in reliefs:
            claimed[relief.vertices] = True
        claimed_faces = claimed[faces].any(axis=1)
        index = len(result)
        result.append(pocket)
        if pocket.top == "through":
            continue
        above_floor = (centre_h - floor > threshold) & inside_contour(face_centres, pocket.contour)
        rising = above_floor & ~claimed_faces
        for part in _parts(context, rising, local=True):
            relief = _measure(context, part, "boss", level=floor, parent=index)
            if relief is not None:
                result.append(relief)
    reliefs = result + reliefs
    for i, relief in enumerate(reliefs):
        if relief.parent is not None:
            reliefs[relief.parent].children.append(i)
    return reliefs


def _parts(context: _Context, chosen_faces: BoolArray, *, local: bool = False) -> list[IntArray]:
    """Connected parts (triangle indices) of the chosen triangles that are local features.

    Chosen triangles connect through shared vertices (meshes with T-junctions share
    no edges there). The feet of two buttons share vertices with the large triangles
    of the plane between them, which are not chosen, so they stay apart.
    """
    chosen = np.flatnonzero(chosen_faces)
    if len(chosen) == 0:
        return []
    labels, count = _face_components(context.faces[chosen])
    parts: list[IntArray] = []
    for label in range(count):
        part_faces = chosen[labels == label]
        part = np.unique(context.faces[part_faces])
        if len(part) < MIN_VERTICES:
            continue
        uv = context.uvh[part, :2]
        extent = np.ptp(uv, axis=0)
        if extent.max() < MIN_EXTENT_MM:
            continue
        if not local:
            outside = context.footprint.find_simplex(uv) < 0
            if outside.mean() > 0.02:
                continue
            if extent[0] * extent[1] > MAX_SHARE * context.extent_area:
                continue
        parts.append(part_faces)
    return parts


def _face_components(faces: IntArray) -> tuple[IntArray, int]:
    """Component label per triangle (0..count-1), triangles joined at shared vertices."""
    used, corner = np.unique(faces.ravel(), return_inverse=True)
    m = len(faces)
    # Bipartite graph: triangle nodes 0..m-1, vertex nodes m..m+len(used)-1.
    rows = np.repeat(np.arange(m), 3)
    graph = sp.csr_matrix(
        (np.ones(3 * m), (rows, m + corner.ravel())), shape=(m + len(used), m + len(used))
    )
    _, labels = connected_components(graph, directed=False)
    _, face_labels = np.unique(labels[:m], return_inverse=True)
    return face_labels.astype(np.int64).ravel(), int(face_labels.max()) + 1 if m else 0


def _measure(
    context: _Context,
    part_faces: IntArray,
    kind: Literal["boss", "pocket"],
    level: float,
    parent: int | None = None,
) -> Relief | None:
    part = np.unique(context.faces[part_faces])
    # Inside a pocket, a part made of the base plane itself is not a feature.
    if level != 0.0 and context.on_plane[part].mean() > ON_PLANE_SHARE:
        return None
    sign = 1.0 if kind == "boss" else -1.0
    rise = sign * (context.uvh[part, 2] - level)
    height = float(np.percentile(rise, HEIGHT_PERCENTILE))
    if height < context.threshold:
        return None
    if not _touches_level(context, part, level):
        return None  # no opening at its level (a hole seen from the far side)
    contour = _section_contour(context, part, level + sign * height / 2.0)
    if contour is None:
        # No closed cut (a channel running out of the part): the part's own boundary.
        contour = _contour(context, part[rise > height / 2.0] if kind == "boss" else part)
    if contour is None:
        return None
    area = abs(signed_area(contour))
    if area < MIN_AREA_MM2:
        return None
    if not _walls_face(context, part, contour, height, outward=kind == "boss"):
        return None
    outline = fit_outline(contour, context.noise)
    top, top_rise = _top(context, part, sign, level, height, area)
    if top_rise is not None:
        height = top_rise  # the flat top itself, free of the percentile's noise bias
    if top == "through":
        # Through: the hole ends at the far side; its points next to the far rim
        # (facing away from the plane) give the depth.
        rim = np.unique(context.graph[part].indices)
        far = rim[context.facing[rim] < -FAR_SIDE]
        if len(far):
            height = max(height, float(np.median(level - context.uvh[far, 2])))
    return Relief(
        kind=kind,
        outline=outline,
        level=level,
        height=height,
        top=top,
        contour=contour,
        vertices=part,
        parent=parent,
    )


def _top(
    context: _Context, part: IntArray, sign: float, level: float, height: float, area: float
) -> tuple[Literal["flat", "domed", "through"], float | None]:
    """The top of a boss or the floor of a pocket, and the height of a flat one.

    The top is made of the triangles near it that face up (out of the material,
    along the plane normal, for both). It is flat when their corners lie on a plane
    parallel to the base; their mean height is then the feature's height.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    faces = context.faces[member[context.faces].any(axis=1)]
    corners = context.uvh[faces]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(normal, axis=1)
    facing = normal[:, 2] / np.maximum(double_area, 1e-300)
    rise = sign * (corners[:, :, 2].mean(axis=1) - level)
    up = (facing > UP_FACING) & (rise > 0.8 * height)
    if 0.5 * float(double_area[up].sum()) < TOP_SHARE * area:
        return ("through" if sign < 0 else "domed"), None
    heights = context.uvh[np.unique(faces[up]), 2]
    if float(np.std(heights)) >= max(FLAT_TOP_FACTOR * context.noise, 0.05):
        return "domed", None
    return "flat", sign * (float(np.mean(heights)) - level)


def _section_contour(context: _Context, part: IntArray, at: float) -> FloatArray | None:
    """The outer closed loop where the plane h = `at` cuts the triangles at the part.

    All triangles touching the part are cut, also those its search left out (a thin
    triangle whose own normal follows the noise), so the loop closes.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    loops = section_loops(context.uvh, context.faces[member[context.faces].any(axis=1)], at)
    if not loops:
        return None
    return max(loops, key=lambda loop: abs(signed_area(loop)))


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


def _contour(context: _Context, members: IntArray) -> FloatArray | None:
    """The outer boundary loop of the faces whose corners are all members (plane frame)."""
    if len(members) < 3:
        return None
    inside = np.zeros(len(context.uvh), dtype=bool)
    inside[members] = True
    faces = context.faces[inside[context.faces].all(axis=1)]
    if len(faces) == 0:
        return None
    loops = boundary_loops(faces)
    if not loops:
        return None
    uv = context.uvh[:, :2]
    outer = max(loops, key=lambda loop: abs(signed_area(uv[loop])))
    result: FloatArray = uv[outer]
    return result


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


def _covered(relief: Relief, inside: BoolArray) -> bool:
    return bool(inside[relief.vertices].mean() > 0.9)


def _rings(corners: FloatArray) -> int:
    """Neighbour rings that span about `NORMAL_SMOOTHING_MM` on this mesh."""
    edge = float(np.mean(np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1)))
    return int(np.clip(round(NORMAL_SMOOTHING_MM / max(edge, 1e-9)), 0, MAX_NORMAL_RINGS))


def face_normals(vertices: FloatArray, faces: IntArray, normals: FloatArray) -> FloatArray:
    """Each triangle's own unit normal and the mean of its smoothed corner normals.

    The own normal is exact on CAD exports but follows the noise on scans with thin
    triangles; the corner mean is robust on scans but blends both sides at the sharp
    edges of CAD exports.
    """
    corners = vertices[faces]
    own = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    result = np.stack([own, normals[faces].sum(axis=1)], axis=1)
    unit: FloatArray = result / np.maximum(np.linalg.norm(result, axis=2, keepdims=True), 1e-300)
    return unit


def vertex_normals(vertices: FloatArray, faces: IntArray, graph: sp.csr_matrix) -> FloatArray:
    """Area-weighted vertex normals, averaged over neighbours `NORMAL_SMOOTHING_MM` away.

    On dense scans single-vertex normals follow the noise (0.02 mm noise on 0.1 mm
    triangles tilts them by tens of degrees); the walls and floors only need the
    direction of the surface around the point. The number of neighbour rings
    follows the edge length, so coarse meshes are not smoothed across whole faces.
    """
    corners = vertices[faces]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    result = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(result, faces[:, corner], normal)
    for _ in range(_rings(corners)):
        result = result + graph @ result
        result /= np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-300)
    length = np.linalg.norm(result, axis=1, keepdims=True)
    normals: FloatArray = result / np.maximum(length, 1e-300)
    return normals


def _touches_level(context: _Context, part: IntArray, level: float) -> bool:
    """Whether the part borders on scan points at its level (its rim reaches it).

    Coarse meshes have wall triangles that run from rim to rim, so the part itself
    may hold only its far rim; its neighbours then lie on the level.
    """
    neighbours = np.unique(context.graph[part].indices)
    near = np.abs(context.uvh[neighbours, 2] - level) < 2.0 * context.threshold
    own = np.abs(context.uvh[part, 2] - level) < 2.0 * context.threshold
    return bool(np.any(near) or np.any(own))


def _walls_face(
    context: _Context, part: IntArray, contour: FloatArray, height: float, *, outward: bool
) -> bool:
    """Whether the part has steep walls facing out of (boss) or into (pocket) the contour.

    The steep wall area must reach `MIN_WALL_SHARE` of perimeter x height. Each wall
    triangle at the part steps a little along its normal from its centre; for a boss
    the step leaves the outline, for a pocket it moves into the opening. Area weights
    keep a bore in a boss from outvoting the larger outer wall on meshes with as many
    points on both.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    touching = context.faces[member[context.faces].any(axis=1)]
    corners = context.uvh[touching]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(normal, axis=1)
    normal /= np.maximum(double_area, 1e-300)[:, None]
    wall = np.abs(normal[:, 2]) < WALL_FACING
    perimeter = float(np.linalg.norm(contour - np.roll(contour, -1, axis=0), axis=1).sum())
    if 0.5 * float(double_area[wall].sum()) < MIN_WALL_SHARE * perimeter * height:
        return False
    sideways = normal[wall, :2]
    sideways /= np.maximum(np.linalg.norm(sideways, axis=1, keepdims=True), 1e-9)
    stepped = corners[wall, :, :2].mean(axis=1) + WALL_STEP_MM * sideways
    weights = double_area[wall]
    inside = float(weights @ inside_contour(stepped, contour) / max(weights.sum(), 1e-300))
    return inside < 0.5 if outward else inside > 0.5
