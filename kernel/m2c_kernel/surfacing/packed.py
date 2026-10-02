"""One B-spline face per layout block, with exactly shared boundary curves.

The limit surface of a net is, on its regular parts, a uniform bicubic B-spline with
one knot span per net quad. Each block of the patch layout (`layout.py`) therefore
becomes one clamped bicubic surface with `spans` knot spans per quad, fitted by least
squares to the dense limit samples of its quads. Where the block touches an irregular
point the limit surface is not polynomial and the fit approximates it.

Boundary curves come first, one per layout line: a cubic spline with `spans` spans per
net edge, fitted to the limit samples along the whole line and pinned to the limit
points at block corners. A block side is a stretch of one line, and the boundary row
of a clamped surface depends only on its boundary poles, so each surface takes the
poles of its line's curve restricted to the side. Neighbouring faces then share their
boundary curves exactly, also where one long side meets several shorter ones
(T-junctions), and every B-Rep edge is the curve of a line between two corners.

Tangents: each line also gets a spline of the limit surface's slope across it. The
second pole ring of a surface follows from that slope, so the faces on both sides of
a line share their tangent plane (and are C1) except near the corners. There a few
poles stay free and are fitted with rows that keep the tangent plane; at irregular
points this leaves kinks of about a degree within half a quad of the point, as the
limit surface itself is not polynomial there (`SPANS` trades that off against size).

Parameters: a block of a x b quads spans [0, a] x [0, b], one unit per quad, and an
edge between corners m net edges apart spans [0, m]; the p-curves are straight lines
of unit speed in the face's parameter plane.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.interpolate import BSpline
from scipy.sparse.linalg import spsolve

from m2c_kernel.cad.occ_compat import BRep_Tool, TopoDS_Shape, gp_Pnt
from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.brep import bspline_curve, bspline_surface, knot_arrays
from m2c_kernel.surfacing.layout import Block, Line, PatchLayout, block_sides, side_on_line
from m2c_kernel.surfacing.occ import (
    BRep_Builder,
    BRepBuilderAPI_MakeEdge,
    BRepLib,
    Geom2d_Line,
    TopAbs_FORWARD,
    TopAbs_REVERSED,
    TopoDS_Face,
    TopoDS_Shell,
    TopoDS_Solid,
    TopoDS_Vertex,
    TopoDS_Wire,
    gp_Dir2d,
    gp_Pnt2d,
)
from m2c_kernel.surfacing.patches import DEGREE
from m2c_kernel.surfacing.subdivision import EdgeTopology

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


SPANS = 4
"""Knot spans per net edge: 4 keeps kinks at irregular points near 1 degree."""
IRREGULAR_LOOSE = 2
"""Free poles of the second ring beside a block corner at an irregular point."""
TANGENT_WEIGHT = 3.0
"""Weight of the tangent-plane rows against the fit to the limit samples (per row)."""
TANGENT_SAMPLES = 8
"""Tangent-plane rows per knot span next to a corner."""
DEGENERATE_SINE = 0.1
"""No tangent rows where a line's tangent and cross slope are nearly parallel."""


class PackingError(ValueError):
    """The layout cannot be built as shared-curve faces (the caller falls back)."""


def clamped_knots(length: int, spans: int) -> FloatArray:
    """Clamped cubic knots on [0, length] with `spans` uniform spans per unit."""
    inner = np.arange(1, length * spans) / spans
    knots: FloatArray = np.concatenate(
        [np.zeros(DEGREE + 1), inner, np.full(DEGREE + 1, float(length))]
    )
    return knots


def greville(knots: FloatArray) -> FloatArray:
    """Greville abscissae: interpolating there recovers a spline in the space exactly."""
    count = len(knots) - DEGREE - 1
    points: FloatArray = np.array([knots[i + 1 : i + DEGREE + 1].mean() for i in range(count)])
    return points


def design(knots: FloatArray, parameters: FloatArray) -> FloatArray:
    matrix: FloatArray = BSpline.design_matrix(parameters, knots, DEGREE).toarray()
    return matrix


@dataclass(frozen=True)
class LineCurve:
    """The cubic spline along one layout line, parameter k at the line's vertex k."""

    spline: BSpline
    length: int
    closed: bool

    def __call__(self, parameters: FloatArray) -> FloatArray:
        if self.closed:
            parameters = np.mod(parameters, self.length)
        points: FloatArray = self.spline(parameters)
        return points

    def derivative(self, parameters: FloatArray) -> FloatArray:
        if self.closed:
            parameters = np.mod(parameters, self.length)
        slopes: FloatArray = self.spline(parameters, nu=1)
        return slopes

    def restricted(self, start: int, step: int, length: int, spans: int) -> FloatArray:
        """Poles of the clamped curve from `start` over `length` edges (step +1 or -1)."""
        knots = clamped_knots(length, spans)
        parameters = greville(knots)
        values = self(start + step * parameters)
        poles: FloatArray = np.linalg.solve(design(knots, parameters), values)
        return poles


@dataclass(frozen=True)
class PackedShape:
    """The B-Rep of a layout and the surface of every block.

    Attributes:
        shape: A `TopoDS_Solid` when the faces close up, otherwise a `TopoDS_Shell`.
        closed: Whether the shell is closed.
        faces: The face of every block, in block order.
        poles: Poles of every block surface, (a * spans + 3, b * spans + 3, 3).
        error: Largest distance between a block surface and the limit samples (mm).
    """

    shape: TopoDS_Shape
    closed: bool
    faces: tuple[Any, ...]
    poles: tuple[FloatArray, ...]
    error: float


def packed_shape(
    grids: FloatArray,
    vertex_limits: FloatArray,
    quads: IntArray,
    topology: EdgeTopology,
    layout: PatchLayout,
    *,
    tolerance: float,
    spans: int = SPANS,
    check_cancelled: Callable[[], None] = lambda: None,
) -> PackedShape:
    """Faces, edges and vertices of the layout, as a solid when they close up.

    Args:
        grids: (p, m + 1, m + 1, 3) limit samples of every net quad (axis 1 from quad
            corner 0 to 1, axis 2 from corner 0 to 3).
        vertex_limits: (n, 3) limit position of every net vertex.
        quads: (p, 4) net quads, oriented outward.
        topology: Edge topology of `quads`.
        layout: Blocks and lines of the net.
        tolerance: Tolerance of the new vertices, edges and faces (mm).
        spans: Knot spans per net edge.
        check_cancelled: Raises when the job is cancelled.
    """
    fitted = [
        _line_curves(line, grids, vertex_limits, quads, topology, layout.corners, spans)
        for line in layout.lines
    ]
    curves = [curve for curve, _ in fitted]
    slopes = [slope for _, slope in fitted]
    check_cancelled()
    valence = np.bincount(topology.edges.ravel(), minlength=topology.n_vertices)
    on_border = np.zeros(topology.n_vertices, dtype=bool)
    on_border[topology.edges[topology.boundary].ravel()] = True
    regular = np.where(on_border, valence == 3, valence == 4)
    poles: list[FloatArray] = []
    error = 0.0
    for block in layout.blocks:
        block_poles, block_error = _block_poles(
            block, grids, curves, slopes, regular, topology, layout, spans
        )
        poles.append(block_poles)
        error = max(error, block_error)
    check_cancelled()
    return _assemble(poles, vertex_limits, curves, topology, layout, spans, tolerance, error)


def _line_samples(
    line: Line, grids: FloatArray, quads: IntArray, topology: EdgeTopology, depth: int
) -> tuple[FloatArray, FloatArray | None, FloatArray | None]:
    """Limit samples along a line and `depth` rows into the quads on both of its sides.

    Returns the parameters and the rows on the left and on the right side (looking
    along the line from outside the material; row 0 is the line itself), each None
    beyond the open border.
    """
    m = grids.shape[1] - 1
    parameters: list[FloatArray] = []
    left: list[FloatArray] = []
    right: list[FloatArray] = []
    for k, edge in enumerate(line.edges):
        parameters.append(k + np.arange(m + 1) / m)
        for face in topology.edge_faces[edge]:
            if face < 0:
                continue
            side = int(np.flatnonzero(topology.face_edges[face] == edge)[0])
            rows = np.stack([_side_rows(grids[face], side, r) for r in range(depth + 1)])
            if quads[face, side] == line.vertices[k]:
                left.append(rows)
            else:
                right.append(rows[:, ::-1])
    t = np.concatenate(parameters)
    on_left = np.concatenate(left, axis=1) if len(left) == len(parameters) else None
    on_right = np.concatenate(right, axis=1) if len(right) == len(parameters) else None
    if on_left is None and on_right is None:
        raise PackingError("a line has quads on neither side")
    return t, on_left, on_right


def _side_rows(grid: FloatArray, side: int, inset: int) -> FloatArray:
    """Samples parallel to one quad side, `inset` rows inside, in the side's direction."""
    last = grid.shape[0] - 1
    match side:
        case 0:
            return grid[:, inset]
        case 1:
            return grid[last - inset, :]
        case 2:
            return grid[::-1, last - inset]
        case _:
            return grid[inset, ::-1]


def _fit_spline(
    t: FloatArray,
    y: FloatArray,
    line: Line,
    spans: int,
    pinned: IntArray | None = None,
    pinned_values: FloatArray | None = None,
) -> LineCurve:
    """Least-squares cubic spline along a line, optionally through pinned vertex values."""
    n = line.length
    if line.closed:
        count = n * spans
        knots = np.arange(-DEGREE, count + DEGREE + 1) / spans
        fold = np.zeros((count + DEGREE, count))
        fold[np.arange(count + DEGREE), (np.arange(count + DEGREE) - DEGREE) % count] = 1.0
        t = np.mod(t, n)
    else:
        knots = clamped_knots(n, spans)
        fold = np.eye(len(knots) - DEGREE - 1)
    basis = design(knots, t) @ fold
    if pinned is None or pinned_values is None or len(pinned) == 0:
        coefficients = np.linalg.lstsq(basis, y, rcond=None)[0]
    else:
        constraint = design(knots, pinned.astype(np.float64)) @ fold
        unknowns = basis.shape[1]
        size = unknowns + len(pinned)
        system = np.zeros((size, size))
        system[:unknowns, :unknowns] = basis.T @ basis
        system[:unknowns, unknowns:] = constraint.T
        system[unknowns:, :unknowns] = constraint
        right = np.concatenate([basis.T @ y, pinned_values])
        coefficients = np.linalg.lstsq(system, right, rcond=None)[0][:unknowns]
    return LineCurve(BSpline(knots, fold @ coefficients, DEGREE), n, line.closed)


def _line_curves(
    line: Line,
    grids: FloatArray,
    vertex_limits: FloatArray,
    quads: IntArray,
    topology: EdgeTopology,
    corners: BoolArray,
    spans: int,
) -> tuple[LineCurve, LineCurve]:
    """The line's curve, pinned to the limit points at corners, and its cross slope.

    The cross slope is the derivative of the limit surface across the line towards
    its left side, per quad width (central differences of the limit samples; one-sided
    on the open border).
    """
    m = grids.shape[1] - 1
    t, left, right = _line_samples(line, grids, quads, topology, depth=2)
    n = line.length
    pinned = np.flatnonzero(corners[line.vertices[: n if line.closed else n + 1]])
    rows = left if left is not None else right
    assert rows is not None
    curve = _fit_spline(t, rows[0], line, spans, pinned, vertex_limits[line.vertices[pinned]])
    if left is not None and right is not None:
        slope = (left[1] - right[1]) * (m / 2.0)
    else:
        inward = (-3.0 * rows[0] + 4.0 * rows[1] - rows[2]) * (m / 2.0)
        slope = inward if left is not None else -inward
    return curve, _fit_spline(t, slope, line, spans)


def _block_samples(block: Block, grids: FloatArray) -> FloatArray:
    """The limit samples of a block's quads as one grid in the block's frame."""
    m = grids.shape[1] - 1
    a, b = block.size
    samples = np.empty((a * m + 1, b * m + 1, 3))
    for i in range(a):
        for j in range(b):
            grid = grids[block.cells[i, j]]
            match int(block.rotations[i, j]):
                case 1:
                    grid = grid[::-1, :].transpose(1, 0, 2)
                case 2:
                    grid = grid[::-1, ::-1]
                case 3:
                    grid = grid[:, ::-1].transpose(1, 0, 2)
            samples[i * m : i * m + m + 1, j * m : j * m + m + 1] = grid
    return samples


def _block_poles(
    block: Block,
    grids: FloatArray,
    curves: list[LineCurve],
    slopes: list[LineCurve],
    regular: BoolArray,
    topology: EdgeTopology,
    layout: PatchLayout,
    spans: int,
) -> tuple[FloatArray, float]:
    """Poles of a block surface.

    The boundary ring comes from the line curves. The next ring comes from the lines'
    cross slopes (the derivative across a clamped boundary is 3 * spans times the
    difference of the first two pole rows), so neighbouring faces meet with the same
    tangent plane. Next to each corner some poles of that ring stay free: one (the
    twist) at a regular point, `IRREGULAR_LOOSE` at an irregular one, where the limit
    surface is not polynomial. They and everything inside are fitted to the limit
    samples by least squares, together with rows that keep the tangent plane along
    the sides near the corners (`_tangent_rows`).
    """
    a, b = block.size
    knots_u, knots_v = clamped_knots(a, spans), clamped_knots(b, spans)
    count_u, count_v = a * spans + DEGREE, b * spans + DEGREE
    poles = np.zeros((count_u, count_v, 3))
    fixed = np.zeros((count_u, count_v), dtype=bool)
    bottom, right, top, left = block_sides(block)
    # Side, its length, boundary row, next row, direction into the block, and how the
    # line's left slope turns into the derivative along the block's own axis.
    rows: tuple[tuple[Any, ...], ...] = (
        (bottom, a, (slice(None), 0), (slice(None), 1), 1.0, 1.0),
        (top, a, (slice(None), -1), (slice(None), -2), -1.0, 1.0),
        (left, b, (0, slice(None)), (1, slice(None)), 1.0, -1.0),
        (right, b, (-1, slice(None)), (-2, slice(None)), -1.0, -1.0),
    )
    places = []
    for side, length, boundary, _, _, _ in rows:
        place = side_on_line(side, layout.lines, layout.edge_line, layout.edge_position, topology)
        if place is None:
            raise PackingError("a block side does not lie on one line")
        line, start, step = place
        poles[boundary] = curves[line].restricted(start, step, length, spans)
        fixed[boundary] = True
        places.append(place)
    loose: list[tuple[int, int]] = []
    for (side, length, boundary, inner, inward, turn), (line, start, step) in zip(
        rows, places, strict=True
    ):
        ends = tuple(1 if regular[side[k]] else IRREGULAR_LOOSE for k in (0, -1))
        loose.append((ends[0], ends[1]))
        derivative = slopes[line].restricted(start, step, length, spans) * (turn * step)
        row = poles[boundary] + inward * derivative / (DEGREE * spans)
        keep = np.zeros(len(row), dtype=bool)
        keep[1 + ends[0] : len(row) - 1 - ends[1]] = True
        target = poles[inner]
        target[keep] = row[keep]
        fixed[inner] |= keep

    m = grids.shape[1] - 1
    samples = _block_samples(block, grids).reshape(-1, 3)
    basis_u = BSpline.design_matrix(np.arange(a * m + 1) / m, knots_u, DEGREE)
    basis_v = BSpline.design_matrix(np.arange(b * m + 1) / m, knots_v, DEGREE)
    basis = sp.kron(basis_u, basis_v, format="csc")
    free = ~fixed.ravel()
    flat = poles.reshape(-1, 3)
    # Unknowns: free poles, coordinates interleaved; the tangent rows mix coordinates.
    index = np.full(free.size, -1, dtype=np.int64)
    index[free] = np.arange(int(free.sum()))
    part = sp.kron(basis[:, free], sp.identity(3), format="csr")
    rest = (samples - basis[:, ~free] @ flat[~free]).ravel()
    tangent, tangent_rest = _tangent_rows(rows, places, loose, poles, index, curves, slopes, spans)
    matrix = sp.vstack([part, tangent]).tocsr()
    right_side = np.concatenate([rest, tangent_rest])
    solution = spsolve((matrix.T @ matrix).tocsc(), matrix.T @ right_side)
    flat[free] = np.asarray(solution).reshape(-1, 3)
    fitted = basis @ flat
    error = float(np.max(np.linalg.norm(fitted - samples, axis=-1)))
    return flat.reshape(count_u, count_v, 3), error


def _tangent_rows(
    rows: tuple[tuple[Any, ...], ...],
    places: list[tuple[int, int, int]],
    loose: list[tuple[int, int]],
    poles: FloatArray,
    index: IntArray,
    curves: list[LineCurve],
    slopes: list[LineCurve],
    spans: int,
) -> tuple[sp.csr_matrix, FloatArray]:
    """Rows that turn the block's tangent plane along its sides into the line's plane.

    Away from the corners the next pole ring already reproduces each line's cross
    slope, so both faces of a line share its tangent plane there. Near a corner some
    poles of that ring are free (`_block_poles`); over the knot spans they influence,
    these rows ask the cross derivative of the face to be perpendicular to the line's
    normal (curve tangent x cross slope), which both neighbouring faces then approach
    in the same way.
    """
    count_u, count_v = poles.shape[:2]
    data: list[float] = []
    row_ids: list[int] = []
    columns: list[int] = []
    right: list[float] = []
    row = 0
    for (_, length, _, _, _, _), (line, start, step), (boundary, inner), ends in zip(
        rows, places, _SIDE_ROWS, loose, strict=True
    ):
        knots = clamped_knots(length, spans)
        near = [
            np.linspace(0.0, (count + 1) / spans, (count + 1) * TANGENT_SAMPLES + 1)[1:]
            for count in ends
        ]
        parameters = np.unique(np.concatenate([near[0], length - near[1]]))
        for parameter in parameters[(parameters > 0) & (parameters < length)]:
            on_line = np.array([start + step * parameter])
            along = curves[line].derivative(on_line)[0]
            across = slopes[line](on_line)[0]
            normal = np.cross(along, across)
            size = float(np.linalg.norm(normal))
            if size < DEGENERATE_SINE * float(np.linalg.norm(along) * np.linalg.norm(across)):
                continue
            normal /= size
            weights = BSpline.design_matrix(np.array([parameter]), knots, DEGREE).toarray()[0]
            fixed_part = 0.0
            for k in np.flatnonzero(weights):
                for pole, sign in ((inner(k), 1.0), (boundary(k), -1.0)):
                    flat = (pole[0] % count_u) * count_v + pole[1] % count_v
                    coefficient = TANGENT_WEIGHT * sign * weights[k]
                    if index[flat] >= 0:
                        for axis in range(3):
                            data.append(coefficient * normal[axis])
                            row_ids.append(row)
                            columns.append(3 * int(index[flat]) + axis)
                    else:
                        fixed_part += coefficient * float(normal @ poles[pole])
            right.append(-fixed_part)
            row += 1
    unknowns = 3 * int(np.count_nonzero(index >= 0))
    matrix = sp.csr_matrix((data, (row_ids, columns)), shape=(row, unknowns))
    return matrix, np.asarray(right)


# Pole (i, j) of the boundary row and of the next row at index k along each side, in
# the order bottom, top, left, right (see `_block_poles`).
_SIDE_ROWS = (
    (lambda k: (k, 0), lambda k: (k, 1)),
    (lambda k: (k, -1), lambda k: (k, -2)),
    (lambda k: (0, k), lambda k: (1, k)),
    (lambda k: (-1, k), lambda k: (-2, k)),
)


@dataclass(frozen=True)
class _Chain:
    """A B-Rep edge: a line between two neighbouring corners."""

    edge: Any
    length: int


def _assemble(
    poles: list[FloatArray],
    vertex_limits: FloatArray,
    curves: list[LineCurve],
    topology: EdgeTopology,
    layout: PatchLayout,
    spans: int,
    tolerance: float,
    error: float,
) -> PackedShape:
    builder = BRep_Builder()
    corners = layout.corners
    vertices: dict[int, Any] = {}
    for index in np.flatnonzero(corners):
        vertex = TopoDS_Vertex()
        builder.MakeVertex(vertex, gp_Pnt(*vertex_limits[index]), tolerance)
        vertices[int(index)] = vertex

    chains: dict[tuple[int, int], _Chain] = {}
    for label, line in enumerate(layout.lines):
        n = line.length
        stops = np.flatnonzero(corners[line.vertices[: n if line.closed else n + 1]])
        if len(stops) == 0 or (not line.closed and (stops[0] != 0 or stops[-1] != n)):
            raise PackingError("a line does not end at corners")
        ends = np.append(stops[1:], stops[0] + n) if line.closed else stops[1:]
        for start, end in zip(stops, ends, strict=False):
            length = int(end - start)
            knots = knot_arrays(clamped_knots(length, spans))
            curve = bspline_curve(curves[label].restricted(int(start), 1, length, spans), knots)
            first = vertices[int(line.vertices[start])]
            last = vertices[int(line.vertices[end % n if line.closed else end])]
            maker = BRepBuilderAPI_MakeEdge(curve, first, last, 0.0, float(length))
            if not maker.IsDone():
                raise PackingError("an edge could not be built")
            chains[(label, int(start))] = _Chain(maker.Edge(), length)

    faces: list[Any] = []
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for block, block_poles in zip(layout.blocks, poles, strict=True):
        a, b = block.size
        surface = bspline_surface(
            block_poles,
            knot_arrays(clamped_knots(a, spans)),
            knot_arrays(clamped_knots(b, spans)),
        )
        face = TopoDS_Face()
        builder.MakeFace(face, surface, tolerance)
        wire = TopoDS_Wire()
        builder.MakeWire(wire)
        for nodes, uv in _boundary(block):
            _add_side(builder, wire, face, nodes, uv, chains, layout, topology, tolerance)
        builder.Add(face, wire)
        builder.Add(shell, face)
        faces.append(face)

    BRepLib.SameParameter_s(shell, tolerance, False)
    closed = bool(BRep_Tool.IsClosed_s(shell))
    shell.Closed(closed)
    if not closed:
        return PackedShape(shell, False, tuple(faces), tuple(poles), error)
    solid = TopoDS_Solid()
    builder.MakeSolid(solid)
    builder.Add(solid, shell)
    BRepLib.OrientClosedSolid_s(solid)
    return PackedShape(solid, True, tuple(faces), tuple(poles), error)


def _boundary(block: Block) -> list[tuple[IntArray, IntArray]]:
    """The four sides in the face's traversal order: nodes and their (u, v)."""
    a, b = block.size
    nodes = block.nodes
    i, j = np.arange(a + 1), np.arange(b + 1)
    return [
        (nodes[:, 0], np.stack([i, np.zeros_like(i)], axis=1)),
        (nodes[-1, :], np.stack([np.full_like(j, a), j], axis=1)),
        (nodes[::-1, -1], np.stack([i[::-1], np.full_like(i, b)], axis=1)),
        (nodes[0, ::-1], np.stack([np.zeros_like(j), j[::-1]], axis=1)),
    ]


def _add_side(
    builder: Any,
    wire: Any,
    face: Any,
    nodes: IntArray,
    uv: IntArray,
    chains: dict[tuple[int, int], _Chain],
    layout: PatchLayout,
    topology: EdgeTopology,
    tolerance: float,
) -> None:
    """Add the edges along one side of a face, split at corners, with their p-curves."""
    stops = [0, *(k for k in range(1, len(nodes) - 1) if layout.corners[nodes[k]]), len(nodes) - 1]
    for first, last in pairwise(stops):
        edge_id = int(topology.edge_ids(nodes[first : first + 1], nodes[first + 1 : first + 2])[0])
        label = int(layout.edge_line[edge_id])
        line = layout.lines[label]
        k = int(layout.edge_position[edge_id])
        forward = bool(line.vertices[k] == nodes[first])
        length = last - first
        start = k if forward else k + 1 - length
        if line.closed:
            start %= line.length
        chain = chains.get((label, start))
        if chain is None or chain.length != length:
            raise PackingError("a face side does not match the edges of its line")
        begin, end = (uv[first], uv[last]) if forward else (uv[last], uv[first])
        direction = (end - begin) / length
        pcurve = Geom2d_Line(
            gp_Pnt2d(float(begin[0]), float(begin[1])),
            gp_Dir2d(float(direction[0]), float(direction[1])),
        )
        builder.UpdateEdge(chain.edge, pcurve, face, tolerance)
        builder.Add(wire, chain.edge.Oriented(TopAbs_FORWARD if forward else TopAbs_REVERSED))


def face_samples(
    shape: PackedShape, layout: PatchLayout, topology: EdgeTopology, per_quad: int
) -> tuple[FloatArray, FloatArray, BoolArray]:
    """Points and unit normals on every face, `per_quad` intervals per quad side.

    The third array marks samples on the net's open border.
    """
    points: list[FloatArray] = []
    normals: list[FloatArray] = []
    border: list[BoolArray] = []
    for block, poles in zip(layout.blocks, shape.poles, strict=True):
        a, b = block.size
        spans = (poles.shape[0] - DEGREE) // a
        knots_u, knots_v = clamped_knots(a, spans), clamped_knots(b, spans)
        u = np.linspace(0.0, a, a * per_quad + 1)
        v = np.linspace(0.0, b, b * per_quad + 1)
        values_u, values_v = design(knots_u, u), design(knots_v, v)
        slopes_u = _derivative_matrix(knots_u, u)
        slopes_v = _derivative_matrix(knots_v, v)
        points.append(np.einsum("ia,abk,jb->ijk", values_u, poles, values_v).reshape(-1, 3))
        along_u = np.einsum("ia,abk,jb->ijk", slopes_u, poles, values_v)
        along_v = np.einsum("ia,abk,jb->ijk", values_u, poles, slopes_v)
        normal = np.cross(along_u, along_v).reshape(-1, 3)
        normals.append(normal / np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-300))
        on_border = np.zeros((len(u), len(v)), dtype=bool)
        bottom, right, top, left = block_sides(block)
        for side, target in (
            (bottom, (slice(None), 0)),
            (top, (slice(None), -1)),
            (left, (0, slice(None))),
            (right, (-1, slice(None))),
        ):
            edge = topology.edge_ids(side[:1], side[1:2])[0]
            on_border[target] = bool(topology.boundary[edge])
        border.append(on_border.ravel())
    return np.concatenate(points), np.concatenate(normals), np.concatenate(border)


def _derivative_matrix(knots: FloatArray, parameters: FloatArray) -> FloatArray:
    count = len(knots) - DEGREE - 1
    matrix: FloatArray = BSpline(knots, np.eye(count), DEGREE)(parameters, nu=1)
    return matrix
