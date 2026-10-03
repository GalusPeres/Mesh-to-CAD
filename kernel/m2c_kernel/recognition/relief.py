"""Reliefs on a base plane: the raised and sunk features a designer would model.

In the plane's frame every vertex has a height h above the plane. Connected parts of
the scan that rise above it (bosses, buttons, ribs) or sink below it (pockets,
recesses, holes) are reliefs when they lie inside the plane's extent; the rest of the
part (side walls, the far side) is not.

For each relief:

- its level is the plane it stands on: the base plane, or the floor of the pocket
  that encloses it (a direction pad's arms stand in a round recess);
- its height (depth) is a high percentile of h above (below) that level;
- its contour is, for a boss, the boundary of the part above half its height (clear
  of rounded feet and tops), for a pocket its mouth; the contour is fitted with a
  simple shape (`outline.py`);
- its top is flat when the upward points near the top lie on a plane parallel to the
  base; a pocket without a floor goes through the part (a through hole).

Sunk parts leave out the triangles facing away from the plane: they belong to the far
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
MIN_VERTICES = 30
MIN_EXTENT_MM = 1.0
ON_PLANE_SHARE = 0.2
FAR_SIDE = 0.5
"""Sunk vertices whose normal points away from the plane beyond this cosine are left out."""
UP_FACING = 0.9
MIN_TOP_POINTS = 3
"""Fewer upward points near the top: no top face (a dome, or a through hole)."""
WALL_FACING = 0.5
WALL_STEP_MM = 0.5
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


def mesh_data(vertices: FloatArray, faces: IntArray) -> MeshData:
    n = len(vertices)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    graph = sp.csr_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    graph = (graph + graph.T).tocsr()
    graph.data[:] = 1.0
    return MeshData(vertices, faces, graph, vertex_normals(vertices, faces, graph))


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
    h = uvh[:, 2]
    sunk = (h < -threshold) & (facing > -FAR_SIDE)
    searches: tuple[tuple[Literal["boss", "pocket"], BoolArray], ...] = (
        ("boss", h > threshold),
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
    for pocket in pockets:
        floor = pocket.level - pocket.height
        inside = _inside_contour(uvh[:, :2], pocket.contour)
        reliefs = [relief for relief in reliefs if not _covered(relief, inside)]
        claimed = np.zeros(n, dtype=bool)
        for relief in reliefs:
            claimed[relief.vertices] = True
        index = len(result)
        result.append(pocket)
        if pocket.top == "through":
            continue
        rising = inside & (h - floor > threshold) & ~claimed
        for part in _parts(context, rising, local=True):
            relief = _measure(context, part, "boss", level=floor, parent=index)
            if relief is not None:
                result.append(relief)
    reliefs = result + reliefs
    for i, relief in enumerate(reliefs):
        if relief.parent is not None:
            reliefs[relief.parent].children.append(i)
    return reliefs


def _parts(context: _Context, members: BoolArray, *, local: bool = False) -> list[IntArray]:
    """Connected parts of the member vertices that are local features of the plane."""
    chosen = np.flatnonzero(members)
    if len(chosen) == 0:
        return []
    sub = context.graph[chosen][:, chosen]
    count, labels = connected_components(sub, directed=False)
    parts: list[IntArray] = []
    for label in range(count):
        part = chosen[labels == label]
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
        parts.append(part)
    return parts


def _measure(
    context: _Context,
    part: IntArray,
    kind: Literal["boss", "pocket"],
    level: float,
    parent: int | None = None,
) -> Relief | None:
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
    # Bosses are outlined at half height (clear of rounded feet and tops); pockets at
    # their mouth, where they cut into the plane they sink from.
    middle = part[rise > height / 2.0] if kind == "boss" else part
    contour = _contour(context, middle)
    if contour is None or abs(_signed_area(contour)) < MIN_AREA_MM2:
        return None
    if not _walls_face(context, part, contour, outward=kind == "boss"):
        return None
    outline = fit_outline(contour, context.noise)
    # The top (a pocket's floor): points near it that face up, out of the material.
    up = context.facing[part] > UP_FACING
    near_top = part[(rise > 0.8 * height) & up]
    top: Literal["flat", "domed", "through"]
    if len(near_top) < MIN_TOP_POINTS:
        top = "through" if kind == "pocket" else "domed"
        if top == "through":
            # Through: the hole ends at the far side; its points next to the far rim
            # (facing away from the plane) give the depth.
            rim = np.unique(context.graph[part].indices)
            far = rim[context.facing[rim] < -FAR_SIDE]
            if len(far):
                height = max(height, float(np.median(level - context.uvh[far, 2])))
    else:
        spread = float(np.std(context.uvh[near_top, 2]))
        top = "flat" if spread < max(FLAT_TOP_FACTOR * context.noise, 0.05) else "domed"
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
    outer = max(loops, key=lambda loop: abs(_signed_area(uv[loop])))
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


def _signed_area(points: FloatArray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1)))


def _inside_contour(points: FloatArray, contour: FloatArray) -> BoolArray:
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
    edge = float(np.mean(np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1)))
    rings = int(np.clip(round(NORMAL_SMOOTHING_MM / max(edge, 1e-9)), 0, MAX_NORMAL_RINGS))
    for _ in range(rings):
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


def _walls_face(context: _Context, part: IntArray, contour: FloatArray, *, outward: bool) -> bool:
    """Whether most wall area faces out of the contour (a boss) or into it (a pocket).

    Each wall triangle at the part steps a little along its normal from its centre;
    for a boss the step leaves the outline, for a pocket it moves into the opening.
    Area weights keep a bore in a boss from outvoting the larger outer wall on
    meshes with as many points on both.
    """
    member = np.zeros(len(context.uvh), dtype=bool)
    member[part] = True
    touching = context.faces[member[context.faces].any(axis=1)]
    corners = context.uvh[touching]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    double_area = np.linalg.norm(normal, axis=1)
    normal /= np.maximum(double_area, 1e-300)[:, None]
    wall = np.abs(normal[:, 2]) < WALL_FACING
    if not np.any(wall):
        return True
    sideways = normal[wall, :2]
    sideways /= np.maximum(np.linalg.norm(sideways, axis=1, keepdims=True), 1e-9)
    stepped = corners[wall, :, :2].mean(axis=1) + WALL_STEP_MM * sideways
    weights = double_area[wall]
    inside = float(weights @ _inside_contour(stepped, contour) / max(weights.sum(), 1e-300))
    return inside < 0.5 if outward else inside > 0.5
