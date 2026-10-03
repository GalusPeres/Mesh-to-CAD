"""Reliefs on a base plane: the raised and sunk features a designer would model.

In the plane's frame every vertex has a height h above the plane. Connected parts of
the scan that rise above it (bosses, buttons, ribs) or sink below it (pockets,
recesses, holes) are reliefs when they lie inside the plane's extent (a feature cut
by the part's outline reaches to its edge); the rest of the part (side walls, the far
side) is not.

For each relief:

- its level is the plane it stands on: the base plane, or the floor of the pocket
  that encloses it (a direction pad's arms stand in a round recess);
- its height (depth) is a high percentile of h above (below) that level;
- its contour is where a cut at half its height (depth) meets the scan, clear of
  rounded or chamfered feet, tops and mouths, and where its sketch is compared with
  the scan; the contour is fitted with a template shape or as a chain of lines and
  arcs (`outline.py`);
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
from scipy.spatial import ConvexHull

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.contours import inside_contour, signed_area
from m2c_kernel.recognition.measure import (
    UP_FACING,
    PlaneContext,
    TopKind,
    boundary_contour,
    section_contour,
    top_of,
    touches_level,
    walls_face,
)
from m2c_kernel.recognition.meshdata import MeshData
from m2c_kernel.recognition.outline import Outline, fit_outline
from m2c_kernel.recognition.planes import BasePlane
from m2c_kernel.recognition.top_surface import TopSurface

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
MIN_AREA_MM2 = 2.0
"""Smaller outlines are scan artefacts, not design features."""
MAX_SHARE = 0.4
"""A relief covers at most this share of its plane's extent."""
OUTSIDE_SHARE = 0.02
"""A relief has at most this share of its points outside the plane's footprint..."""
OUTSIDE_MARGIN_MM = 0.5
"""...farther out than this (the rounding of the part's outline)."""
HEIGHT_PERCENTILE = 95.0


@dataclass(frozen=True)
class Relief:
    """A raised or sunk feature on a base plane.

    Attributes:
        kind: "boss" rises from its level, "pocket" sinks below it (a hole when
            `top` is "through").
        outline: Fitted contour shape in the plane's (u, v) frame.
        level: Height of the plane it stands on, above the base plane (mm).
        height: Height above (boss) or depth below (pocket) the level (mm), of an
            inclined top at the contour's centre.
        top: "flat", "inclined" or "domed" (for pockets: the floor), "through" for
            a pocket without a floor.
        contour: (k, 2) measured contour in the plane frame.
        vertices: Scan vertices of the feature.
        top_surface: The heights of a flat, inclined or smoothly domed top (plane
            frame), None for others; `height` holds at its centre.
        parent: Index of the enclosing pocket, if any.
    """

    kind: Literal["boss", "pocket"]
    outline: Outline
    level: float
    height: float
    top: TopKind
    contour: FloatArray
    vertices: IntArray
    top_surface: TopSurface | None = None
    parent: int | None = None
    children: list[int] = field(default_factory=list)

    def top_at(self, uv: FloatArray) -> FloatArray:
        """Height of the top (a pocket's floor) above the base plane at (k, 2) points.

        The surface's shape at the feature's height (which design intent may round).
        """
        sign = 1.0 if self.kind == "boss" else -1.0
        top = self.level + sign * self.height
        if self.top_surface is None:
            return np.full(len(uv), top)
        surface = self.top_surface
        result: FloatArray = top + surface.height(uv) - surface.coefficients[0]
        return result

    def top_gradient(self, uv: FloatArray) -> FloatArray:
        """(k, 2) rise of the top per mm along u and v."""
        if self.top_surface is None:
            return np.zeros((len(uv), 2))
        return self.top_surface.gradient(uv)

    @property
    def tilt(self) -> float:
        """Angle of an inclined top against the base plane at its centre (radians)."""
        return self.top_surface.tilt() if self.top_surface and self.top == "inclined" else 0.0


def find_reliefs(data: MeshData, plane: BasePlane, noise: float) -> list[Relief]:
    """Raised and sunk features on the plane, pockets with the features inside them."""
    vertices, faces, graph = data.vertices, data.faces, data.graph
    uvh = plane.to_plane(vertices)
    inlier_vertices = np.unique(faces[plane.faces])
    n = len(vertices)
    threshold = max(MIN_RISE_MM, RISE_NOISE * noise)
    span = np.ptp(uvh[inlier_vertices, :2], axis=0)
    on_plane = np.zeros(n, dtype=bool)
    on_plane[inlier_vertices] = True
    normals = data.normals
    facing = normals @ plane.normal
    # The footprint is everything flat at the plane's height, not only its inliers: a
    # scanned face warps away from its plane towards its ends, where features cut by
    # the part's outline (a button half off the edge) stand.
    flat = on_plane | ((np.abs(uvh[:, 2]) < threshold) & (facing > UP_FACING))
    footprint = ConvexHull(uvh[flat, :2]).equations
    context = PlaneContext(
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


def _parts(
    context: PlaneContext, chosen_faces: BoolArray, *, local: bool = False
) -> list[IntArray]:
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
            beyond = (context.footprint[:, :2] @ uv.T + context.footprint[:, 2:]).max(axis=0)
            if np.mean(beyond > OUTSIDE_MARGIN_MM) > OUTSIDE_SHARE:
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
    context: PlaneContext,
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
    if not touches_level(context, part, level):
        return None  # no opening at its level (a hole seen from the far side)
    contour = section_contour(context, part, level + sign * height / 2.0)
    if contour is None:
        # No closed cut (a channel running out of the part): the part's own boundary.
        contour = boundary_contour(context, part[rise > height / 2.0] if kind == "boss" else part)
    if contour is None:
        return None
    area = abs(signed_area(contour))
    if area < MIN_AREA_MM2:
        return None
    if not walls_face(context, part, contour, height, outward=kind == "boss"):
        return None
    measured_at = height
    top = top_of(context, part, sign, level, height, area)
    if top.surface is not None:
        # The top itself at its centre, free of the percentile's noise bias.
        height = sign * (top.surface.coefficients[0] - level)
    if top.kind == "through":
        # Through: the hole ends at the far side; its points next to the far rim
        # (facing away from the plane) give the depth.
        rim = np.unique(context.graph[part].indices)
        far = rim[context.facing[rim] < -FAR_SIDE]
        if len(far):
            height = max(height, float(np.median(level - context.uvh[far, 2])))
    if height != measured_at:
        # Measured again where its sketch compares with the scan: at half the final
        # height, which differs from the percentile's on drafted or rounded walls.
        again = section_contour(context, part, level + sign * height / 2.0)
        if again is not None and abs(signed_area(again)) >= MIN_AREA_MM2:
            contour = again
    outline = fit_outline(contour, context.noise)
    return Relief(
        kind=kind,
        outline=outline,
        level=level,
        height=height,
        top=top.kind,
        contour=contour,
        top_surface=top.surface,
        vertices=part,
        parent=parent,
    )


def _covered(relief: Relief, inside: BoolArray) -> bool:
    return bool(inside[relief.vertices].mean() > 0.9)
