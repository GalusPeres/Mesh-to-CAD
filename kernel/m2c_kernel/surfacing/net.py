"""Freeform nets: editable quad control cages whose limit surface is the CAD surface.

A net is a quad mesh of control points. Its Catmull-Clark limit surface is smooth
(curvature-continuous away from irregular points, tangent-continuous at them), and on
regular parts it is exactly a bicubic B-spline surface. The user sees the limit
surface, drags control points and asks the net to snap to the scan; the CAD shape is
a network of bicubic B-spline patches through the limit surface (`patches.py`,
`brep.py`), a solid when the net is closed and an open shell otherwise.

- `generate_net`: a clean field-aligned net on the scan or on selected triangles
  (Instant Meshes, `quadmesh.py`), fitted to the scan.
- `fit_net`: snap a net to the scan (all points, or with some held in place).
- `limit_map`: the sparse map from control points to a dense limit-surface mesh, so
  the renderer can redraw the surface while a point is dragged without asking the
  kernel; plus the lines of the net drawn on the surface.
- `net_shape`: the B-Rep of a net: one face per rectangle of the patch layout
  (`layout.py`, `packed.py`), or one face per quad if the layout cannot be built.
- `net_deviation`: distances of scan points to the net's surface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.spatial import cKDTree

from m2c_kernel.cad.occ_compat import BRepCheck_Analyzer, TopoDS_Shape
from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.brep import build_shape
from m2c_kernel.surfacing.fitting import fit_cage, scan_samples
from m2c_kernel.surfacing.layout import patch_layout
from m2c_kernel.surfacing.packed import PackingError, face_samples, packed_shape
from m2c_kernel.surfacing.patches import interpolate_patches
from m2c_kernel.surfacing.quadmesh import QuadNet, Remesher, quad_net
from m2c_kernel.surfacing.subdivision import (
    EdgeTopology,
    PatchHierarchy,
    edge_topology,
    grid_cells,
    patch_hierarchy,
)

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]

FIT_LEVEL = 2
"""Limit samples per net quad used for fitting: (2^2 + 1)^2."""
PATCH_LEVEL = 3
"""Limit samples per net quad the B-spline patches interpolate: (2^3 + 1)^2."""
DISPLAY_QUADS_FINE = 1500
"""Up to this many quads the renderer gets level 3 (64 cells per quad), above level 2."""
MAX_FIT_POINTS = 400_000
DEFAULT_SMOOTHING = 0.002
DEFAULT_ITERATIONS = 6
DEVIATION_SAMPLES = 17
SHAPE_TOLERANCE = 1e-6


class NetError(ValueError):
    """The quads do not form an oriented 2-manifold net."""


def checked_topology(quads: IntArray, n_vertices: int) -> EdgeTopology:
    """Edge topology of a net; every vertex must be used."""
    from m2c_kernel.surfacing.subdivision import TopologyError

    if quads.ndim != 2 or quads.shape[1] != 4 or len(quads) == 0:
        raise NetError("a net needs quads")
    if quads.min() < 0 or quads.max() >= n_vertices:
        raise NetError("quad index out of range")
    if len(np.unique(quads)) != n_vertices:
        raise NetError("unused vertices")
    try:
        return edge_topology(quads, n_vertices)
    except TopologyError as error:
        raise NetError(str(error)) from error


# Generation and fitting -------------------------------------------------------------------


def generate_net(
    vertices: FloatArray,
    faces: IntArray,
    normals: FloatArray,
    target_quads: int,
    *,
    crease_deg: float = 0.0,
    smoothing: float = DEFAULT_SMOOTHING,
    iterations: int = DEFAULT_ITERATIONS,
    remesh: Remesher | None = None,
    check_cancelled: Callable[[], None] = lambda: None,
    progress: Callable[[float], None] = lambda _: None,
) -> QuadNet:
    """A clean net on the triangles, with its limit surface fitted to them."""
    net = quad_net(
        vertices,
        faces,
        normals,
        target_quads,
        crease_deg=crease_deg,
        remesh=remesh,
        check_cancelled=check_cancelled,
    )
    progress(0.4)
    fitted = fit_net(
        net.vertices,
        net.quads,
        vertices,
        normals,
        smoothing=smoothing,
        iterations=iterations,
        check_cancelled=check_cancelled,
        progress=lambda share: progress(0.4 + 0.6 * share),
    )
    return QuadNet(fitted, net.quads)


def fit_net(
    cage: FloatArray,
    quads: IntArray,
    scan_points: FloatArray,
    scan_normals: FloatArray,
    *,
    fixed: BoolArray | None = None,
    smoothing: float = DEFAULT_SMOOTHING,
    iterations: int = DEFAULT_ITERATIONS,
    check_cancelled: Callable[[], None] = lambda: None,
    progress: Callable[[float], None] = lambda _: None,
) -> FloatArray:
    """Move the control points so that the limit surface follows the scan points.

    `fixed` control points stay where they are. On an open net, scan points beyond
    the border do not drag the border outwards (`fitting.py`).
    """
    topology = checked_topology(quads, len(cage))
    hierarchy = patch_hierarchy(quads, len(cage), FIT_LEVEL)
    stride = max(1, -(-len(scan_points) // MAX_FIT_POINTS))
    scan = scan_samples(scan_points[::stride], scan_normals[::stride])
    border = _border_vertices(hierarchy, topology) if np.any(topology.boundary) else None
    return fit_cage(
        cage,
        quads,
        hierarchy,
        scan,
        smoothing=smoothing,
        iterations=iterations,
        fixed=fixed,
        border=border,
        check_cancelled=check_cancelled,
        progress=lambda state: progress(state.iteration / state.iterations),
    )


def _border_vertices(hierarchy: PatchHierarchy, topology: EdgeTopology) -> BoolArray:
    """Per fine vertex of the hierarchy: True on a boundary edge of the net."""
    border = np.zeros(hierarchy.n_vertices, dtype=bool)
    for side in range(4):
        open_side = topology.boundary[topology.face_edges[:, side]]
        border[_side_rows(hierarchy.grids, side)[open_side].ravel()] = True
    return border


def _side_rows(grids: IntArray, side: int) -> IntArray:
    """Fine vertices along side `side` of every patch, in the side's traversal direction."""
    match side:
        case 0:
            return grids[:, :, 0]
        case 1:
            return grids[:, -1, :]
        case 2:
            return grids[:, ::-1, -1]
        case _:
            return grids[:, 0, ::-1]


# Display ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitMap:
    """A dense mesh on the limit surface as a linear map of the control points.

    Attributes:
        matrix: (fine vertices, control points) sparse map; row i of a control point
            index i is that point's own limit position.
        triangles: (t, 3) triangles of the dense mesh, oriented like the net.
        segments: (s, 2) dense vertex pairs along the net's edges (the net drawn on
            the surface).
        segment_edges: (s,) net edge of every segment.
        edges: (e, 2) control-point pairs of the net's edges.
        boundary_edges: (e,) True for edges with only one quad.
        border: (fine vertices,) True on the net's open border.
        face_edges: (e,) True for net edges on a border between CAD faces (the patch
            layout), drawn as the faces' outlines while the net is edited.
        face_count: Number of CAD faces the net becomes.
        level: Subdivision level of the dense mesh.
    """

    matrix: sp.csr_matrix
    triangles: IntArray
    segments: IntArray
    segment_edges: IntArray
    edges: IntArray
    boundary_edges: BoolArray
    border: BoolArray
    face_edges: BoolArray
    face_count: int
    level: int


def limit_map(quads: IntArray, n_vertices: int, level: int | None = None) -> LimitMap:
    topology = checked_topology(quads, n_vertices)
    if level is None:
        level = 3 if len(quads) <= DISPLAY_QUADS_FINE else 2
    hierarchy = patch_hierarchy(quads, n_vertices, level)
    cells = grid_cells(hierarchy.grids)
    triangles = np.concatenate([cells[:, [0, 1, 2]], cells[:, [0, 2, 3]]])
    segment_rows: list[IntArray] = []
    segment_edges: list[IntArray] = []
    for side in range(4):
        rows = _side_rows(hierarchy.grids, side)
        pairs = np.stack([rows[:, :-1], rows[:, 1:]], axis=-1)
        segment_rows.append(pairs.reshape(-1, 2))
        segment_edges.append(np.repeat(topology.face_edges[:, side], rows.shape[1] - 1))
    segments = np.concatenate(segment_rows)
    edges_of_segments = np.concatenate(segment_edges)
    # Interior net edges appear on both of their quads; keep each dense segment once.
    keys = np.sort(segments, axis=1)
    _, first = np.unique(keys[:, 0] * hierarchy.n_vertices + keys[:, 1], return_index=True)
    first.sort()
    layout = patch_layout(quads, topology)
    return LimitMap(
        matrix=hierarchy.sample_matrix(),
        triangles=triangles.astype(np.int64),
        segments=segments[first],
        segment_edges=edges_of_segments[first],
        edges=topology.edges,
        boundary_edges=topology.boundary,
        border=_border_vertices(hierarchy, topology),
        face_edges=layout.edge_line >= 0,
        face_count=len(layout.blocks),
        level=level,
    )


# CAD shape and deviation ------------------------------------------------------------------


@dataclass(frozen=True)
class NetShape:
    """The B-Rep of a net and dense samples of its faces.

    Attributes:
        shape: A solid when the net is closed, otherwise an open shell (a compound of
            shells when the net has separate pieces).
        closed: Whether the net is closed.
        faces: The B-Rep faces, in layout block order (or quad order when unpacked).
        samples: (k, 3) points on the faces, for deviation measurements.
        normals: (k, 3) unit normals at `samples`.
        on_border: (k,) True for samples on the net's open border.
        packed: One face per layout rectangle; False when it fell back to one per quad.
    """

    shape: TopoDS_Shape
    closed: bool
    faces: tuple[Any, ...]
    samples: FloatArray
    normals: FloatArray
    on_border: BoolArray
    packed: bool


def net_pieces(quads: IntArray, n_vertices: int) -> list[IntArray]:
    """Quad indices of the net's connected pieces (quads sharing a point belong together)."""
    from scipy.sparse.csgraph import connected_components

    count = len(quads)
    rows = np.repeat(np.arange(count), 4)
    incidence = sp.coo_matrix(
        (np.ones(rows.size), (rows, count + quads.ravel())),
        shape=(count + n_vertices, count + n_vertices),
    )
    _, labels = connected_components(incidence, directed=False)
    quad_labels = labels[:count]
    return [np.flatnonzero(quad_labels == label) for label in np.unique(quad_labels)]


def net_shape(
    cage: FloatArray,
    quads: IntArray,
    check_cancelled: Callable[[], None] = lambda: None,
    *,
    packed: bool = True,
) -> NetShape:
    """The CAD shape of a net: few large faces where the layout allows it.

    A net still being built often has several separate pieces; each becomes its own
    shape and they are kept together as one open compound (never one shell, which
    must be connected).
    """
    checked_topology(quads, len(cage))
    pieces = net_pieces(quads, len(cage))
    if len(pieces) == 1:
        return _piece_shape(cage, quads, check_cancelled, packed=packed)
    shapes = []
    for piece in pieces:
        used, local = np.unique(quads[piece], return_inverse=True)
        sub = _piece_shape(cage[used], local.reshape(-1, 4), check_cancelled, packed=packed)
        shapes.append(sub)
    return _joined(shapes)


def _joined(shapes: list[NetShape]) -> NetShape:
    """Separate pieces as one open compound."""
    from m2c_kernel.surfacing.occ import BRep_Builder, TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape.shape)
    return NetShape(
        compound,
        False,
        tuple(face for shape in shapes for face in shape.faces),
        np.concatenate([shape.samples for shape in shapes]),
        np.concatenate([shape.normals for shape in shapes]),
        np.concatenate([shape.on_border for shape in shapes]),
        all(shape.packed for shape in shapes),
    )


def _piece_shape(
    cage: FloatArray,
    quads: IntArray,
    check_cancelled: Callable[[], None],
    *,
    packed: bool,
) -> NetShape:
    """The CAD shape of one connected piece of a net."""
    topology = checked_topology(quads, len(cage))
    hierarchy = patch_hierarchy(quads, len(cage), PATCH_LEVEL)
    limit = hierarchy.limit_points(cage)
    grids = limit[hierarchy.grids]
    check_cancelled()
    if packed:
        layout = patch_layout(quads, topology, check_cancelled)
        try:
            result = packed_shape(
                grids,
                limit[: len(cage)],
                quads,
                topology,
                layout,
                tolerance=SHAPE_TOLERANCE,
                check_cancelled=check_cancelled,
            )
        except PackingError:
            result = None
        if result is not None and BRepCheck_Analyzer(result.shape).IsValid():
            samples, normals, on_border = face_samples(
                result, layout, topology, DEVIATION_SAMPLES - 1
            )
            return NetShape(
                result.shape, result.closed, result.faces, samples, normals, on_border, True
            )
    network = interpolate_patches(grids)
    patches = build_shape(network, quads, topology, SHAPE_TOLERANCE, check_cancelled)
    samples, normals = network.evaluate(np.linspace(0.0, 1.0, DEVIATION_SAMPLES))
    on_border = np.zeros(samples.shape[:3], dtype=bool)
    open_side = topology.boundary[topology.face_edges]
    on_border[open_side[:, 0], :, 0] = True
    on_border[open_side[:, 1], -1, :] = True
    on_border[open_side[:, 2], :, -1] = True
    on_border[open_side[:, 3], 0, :] = True
    return NetShape(
        patches.shape,
        patches.closed,
        patches.faces,
        samples.reshape(-1, 3),
        normals.reshape(-1, 3),
        on_border.ravel(),
        False,
    )


COVER_DISTANCE_MM = 2.0
"""Scan points farther from every surface sample are not covered by the net."""


@dataclass(frozen=True)
class NetDeviation:
    """Unsigned distances of the covered scan points to the net's surface (mm).

    Points whose nearest surface sample lies on the open border of the net are
    outside the net and not counted.
    """

    rms: float
    mean: float
    p95: float
    max: float
    count: int


def net_deviation(shape: NetShape, points: FloatArray) -> NetDeviation | None:
    """Point-to-surface distances: nearest dense surface sample, then its tangent plane.

    Only scan points near the net count: a small net on the top of a part must not be
    measured against its bottom far below (as the heatmap in the tool, which looks
    COVER_DISTANCE_MM around the surface).
    """
    reach, index = cKDTree(shape.samples).query(
        points, distance_upper_bound=COVER_DISTANCE_MM, workers=-1
    )
    near = np.isfinite(reach)
    points, index = points[near], index[near]
    covered = ~shape.on_border[index]
    if not np.any(covered):
        return None
    offset = points[covered] - shape.samples[index[covered]]
    distance = np.abs(np.einsum("ij,ij->i", offset, shape.normals[index[covered]]))
    return NetDeviation(
        rms=float(np.sqrt(np.mean(distance**2))),
        mean=float(np.mean(distance)),
        p95=float(np.percentile(distance, 95)),
        max=float(np.max(distance)),
        count=len(distance),
    )
