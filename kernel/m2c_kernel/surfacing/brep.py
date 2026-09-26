"""A B-Rep shell (or solid) from a patch network and the quad topology of its cage.

The shell is assembled directly instead of being sewn: every cage vertex becomes one
B-Rep vertex, every cage edge one B-Rep edge whose 3D curve is the boundary curve of
the first patch that uses it, and every patch one face bounded by its four edges,
with straight parameter lines as p-curves. Neighbouring patches share their boundary
curves up to rounding (see `patches.py`), so the topology is exact and the
tolerances stay at the modelling precision; sewing would have to rediscover the
same adjacency by geometry, which is slower and can merge the wrong edges where two
sheets of a thin part come close.

Patch sides: side i runs from quad corner i to corner i + 1, i.e. v = 0 (u rising),
u = 1 (v rising), v = 1 (u falling), u = 0 (v falling).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from m2c_kernel.cad.occ_compat import BRep_Tool, TopoDS_Shape, gp_Pnt
from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.occ import (
    Array1_double,
    Array1_gp_Pnt,
    Array1_int,
    Array2_gp_Pnt,
    BRep_Builder,
    BRepBuilderAPI_MakeEdge,
    BRepLib,
    Geom2d_Line,
    Geom_BSplineCurve,
    Geom_BSplineSurface,
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
from m2c_kernel.surfacing.patches import DEGREE, PatchNetwork
from m2c_kernel.surfacing.subdivision import EdgeTopology

type IntArray = npt.NDArray[np.int64]

# p-curve of each side when the edge's 3D curve runs along the face's own traversal:
# start point and direction in (u, v). Traversed the other way, the start is the end
# and the direction flips.
_SIDE_START = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
_SIDE_DIRECTION = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))


@dataclass(frozen=True)
class PatchShape:
    """The assembled B-Rep and the order of its faces.

    Attributes:
        shape: A `TopoDS_Solid` when the patches close up, otherwise a `TopoDS_Shell`.
        closed: Whether the shell is closed.
        faces: The face of every patch, in patch order.
    """

    shape: TopoDS_Shape
    closed: bool
    faces: tuple[Any, ...]


def side_poles(poles: FloatArray, side: int) -> FloatArray:
    """Boundary poles of one patch side, in the side's traversal direction."""
    match side:
        case 0:
            return poles[:, 0]
        case 1:
            return poles[-1, :]
        case 2:
            return poles[::-1, -1]
        case _:
            return poles[0, ::-1]


def _knot_arrays(knots: FloatArray) -> tuple[Any, Any]:
    values, multiplicities = np.unique(knots, return_counts=True)
    knot_array, mult_array = Array1_double(1, len(values)), Array1_int(1, len(values))
    for index, (value, multiplicity) in enumerate(zip(values, multiplicities, strict=True), 1):
        knot_array.SetValue(index, float(value))
        mult_array.SetValue(index, int(multiplicity))
    return knot_array, mult_array


def bspline_surface(poles: FloatArray, knots: tuple[Any, Any]) -> Any:
    count_u, count_v = poles.shape[:2]
    array = Array2_gp_Pnt(1, count_u, 1, count_v)
    for i in range(count_u):
        for j in range(count_v):
            array.SetValue(i + 1, j + 1, gp_Pnt(*poles[i, j]))
    knot_array, mult_array = knots
    return Geom_BSplineSurface(
        array, knot_array, knot_array, mult_array, mult_array, DEGREE, DEGREE
    )


def bspline_curve(poles: FloatArray, knots: tuple[Any, Any]) -> Any:
    array = Array1_gp_Pnt(1, len(poles))
    for index, point in enumerate(poles, 1):
        array.SetValue(index, gp_Pnt(*point))
    knot_array, mult_array = knots
    return Geom_BSplineCurve(array, knot_array, mult_array, DEGREE)


def _pcurve(side: int, forward: bool) -> Any:
    start, direction = _SIDE_START[side], _SIDE_DIRECTION[side]
    if not forward:
        end = _SIDE_START[(side + 1) % 4]
        start, direction = end, (-direction[0], -direction[1])
    return Geom2d_Line(gp_Pnt2d(*start), gp_Dir2d(*direction))


def build_shape(
    network: PatchNetwork,
    quads: IntArray,
    topology: EdgeTopology,
    tolerance: float,
    check_cancelled: Callable[[], None] = lambda: None,
) -> PatchShape:
    """Faces, edges and vertices of the patch network, as a solid when it is closed.

    Args:
        network: One patch per quad, in quad order.
        quads: (p, 4) cage quads, consistently oriented outward.
        topology: Edge topology of `quads`.
        tolerance: Tolerance of the new vertices, edges and faces (mm).
        check_cancelled: Raises when the job is cancelled.
    """
    builder = BRep_Builder()
    knots = _knot_arrays(network.knots)
    poles = network.poles

    corner_points = np.stack(
        [poles[:, 0, 0], poles[:, -1, 0], poles[:, -1, -1], poles[:, 0, -1]], axis=1
    )
    vertex_points = np.zeros((int(quads.max()) + 1, 3))
    vertex_points[quads.ravel()] = corner_points.reshape(-1, 3)
    vertices: dict[int, Any] = {}
    for index in np.unique(quads):
        vertex = TopoDS_Vertex()
        builder.MakeVertex(vertex, gp_Pnt(*vertex_points[index]), tolerance)
        vertices[int(index)] = vertex

    owner = topology.edge_faces[:, 0]
    owner_side = np.argmax(topology.face_edges[owner] == np.arange(len(owner))[:, None], axis=1)
    edges: list[Any] = []
    for edge_id, (face, side) in enumerate(zip(owner, owner_side, strict=True)):
        if edge_id % 512 == 0:
            check_cancelled()
        curve = bspline_curve(side_poles(poles[face], int(side)), knots)
        start = vertices[int(quads[face, side])]
        end = vertices[int(quads[face, (side + 1) % 4])]
        maker = BRepBuilderAPI_MakeEdge(curve, start, end, 0.0, 1.0)
        if not maker.IsDone():
            raise RuntimeError(f"edge {edge_id} could not be built")
        edges.append(maker.Edge())

    faces: list[Any] = []
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for patch in range(len(quads)):
        if patch % 256 == 0:
            check_cancelled()
        face = TopoDS_Face()
        builder.MakeFace(face, bspline_surface(poles[patch], knots), tolerance)
        wire = _wire(builder, face, patch, topology, owner, owner_side, edges, tolerance)
        builder.Add(face, wire)
        builder.Add(shell, face)
        faces.append(face)

    BRepLib.SameParameter_s(shell, tolerance, False)
    closed = bool(BRep_Tool.IsClosed_s(shell))
    shell.Closed(closed)
    if not closed:
        return PatchShape(shape=shell, closed=False, faces=tuple(faces))
    solid = TopoDS_Solid()
    builder.MakeSolid(solid)
    builder.Add(solid, shell)
    BRepLib.OrientClosedSolid_s(solid)
    return PatchShape(shape=solid, closed=True, faces=tuple(faces))


def _wire(
    builder: Any,
    face: Any,
    patch: int,
    topology: EdgeTopology,
    owner: IntArray,
    owner_side: IntArray,
    edges: list[Any],
    tolerance: float,
) -> Any:
    wire = TopoDS_Wire()
    builder.MakeWire(wire)
    for side in range(4):
        edge_id = int(topology.face_edges[patch, side])
        forward = bool(owner[edge_id] == patch and owner_side[edge_id] == side)
        edge = edges[edge_id]
        builder.UpdateEdge(edge, _pcurve(side, forward), face, tolerance)
        builder.Add(wire, edge.Oriented(TopAbs_FORWARD if forward else TopAbs_REVERSED))
    return wire
