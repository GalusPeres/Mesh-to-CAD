"""Loft ends at planes: a rounded block whose top edge is rounded too.

The loft takes its sections from the straight walls; up to a plane the walls continue
straight and end in it, past the top rounding of the scan.
"""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from m2c_kernel.cad.check import check_solid
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.ends import PlaneEnd
from m2c_kernel.freeform.loft import LoftAxis, ScanLoft, loft_scan
from m2c_kernel.protocol.errors import KernelError
from tests.freeform.shapes import FloatArray, IntArray
from tests.freeform.test_loft_corners import wall_points
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

Z = np.array([0.0, 0.0, 1.0])
SIZE = (60.0, 30.0, 20.0)
CORNER_MM = 8.0
TOP_MM = 2.0
AREA = SIZE[0] * SIZE[1] - (4.0 - np.pi) * CORNER_MM**2
"""Of the outline: a rectangle with CORNER_MM corners."""


def edges_of(shape: object) -> list[object]:
    explorer, found = TopExp_Explorer(shape, TopAbs_EDGE), []
    while explorer.More():
        found.append(TopoDS.Edge(explorer.Current()))
        explorer.Next()
    return found


def rounded_block(top: float) -> object:
    """Vertical edges rounded by CORNER_MM, the top edges by `top`."""
    shape = BRepPrimAPI_MakeBox(gp_Pnt(-SIZE[0] / 2, -SIZE[1] / 2, 0.0), *SIZE).Shape()
    maker = BRepFilletAPI_MakeFillet(shape)
    for edge in edges_of(shape):
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.99:
            maker.Add(CORNER_MM, edge)
    shape = maker.Shape()
    if top > 0.0:
        maker = BRepFilletAPI_MakeFillet(shape)
        for edge in edges_of(shape):
            curve = BRepAdaptor_Curve(edge)
            ends = (curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter()))
            if all(abs(point.Z() - SIZE[2]) < 1e-6 for point in ends):
                maker.Add(top, edge)
        shape = maker.Shape()
    return shape


@cache
def block() -> tuple[FloatArray, IntArray]:
    part = tessellate_part(rounded_block(TOP_MM), 1.0)
    return part.vertices, part.faces


def plane(z: float, normal: tuple[float, float, float] = (0.0, 0.0, 1.0)) -> PlaneEnd:
    return PlaneEnd(np.array([0.0, 0.0, z]), np.asarray(normal))


def lofted(start: PlaneEnd | None, end: PlaneEnd | None) -> ScanLoft:
    vertices, faces = block()
    axis = LoftAxis(np.zeros(3), Z)
    return loft_scan(vertices, faces, axis, 3.0, 15.0, 12, start_plane=start, end_plane=end)


def outline_distance(points: FloatArray) -> FloatArray:
    inner = np.array([SIZE[0] / 2, SIZE[1] / 2]) - CORNER_MM
    q = np.abs(points[:, :2]) - inner
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(q.max(axis=1), 0.0)
    result: FloatArray = np.abs(outside - CORNER_MM)
    return result


def cap_normal(cap: object) -> FloatArray:
    surface = BRepAdaptor_Surface(TopoDS.Face(cap))
    assert surface.GetType() == GeomAbs_Plane
    direction = surface.Plane().Axis().Direction()
    return np.array([direction.X(), direction.Y(), direction.Z()])


@cache
def to_both_planes() -> ScanLoft:
    return lofted(plane(0.0), plane(SIZE[2]))


def test_walls_reach_planes_beyond_the_range() -> None:
    result = to_both_planes()
    check = check_solid(result.solid.shape)
    assert check.valid and check.solids == 1
    assert check.volume == pytest.approx(AREA * SIZE[2], rel=5e-4)
    points = wall_points(result.solid.lateral[0])
    assert points[:, 2].min() == pytest.approx(0.0, abs=1e-6)
    assert points[:, 2].max() == pytest.approx(SIZE[2], abs=1e-6)
    # Straight on past the scan's top rounding, not into it.
    assert outline_distance(points).max() < 0.02
    for cap in (result.solid.start_cap, result.solid.end_cap):
        assert abs(cap_normal(cap) @ Z) == pytest.approx(1.0, abs=1e-9)


def test_a_plane_inside_the_range_ends_the_loft_there() -> None:
    result = lofted(None, plane(10.0, (0.0, 0.0, -1.0)))
    check = check_solid(result.solid.shape)
    assert check.valid
    assert check.volume == pytest.approx(AREA * 7.0, rel=1e-3)
    assert result.heights.max() < 10.0
    assert wall_points(result.solid.lateral[0])[:, 2].max() == pytest.approx(10.0, abs=1e-6)


def test_a_tilted_plane() -> None:
    tilt = np.radians(15.0)
    normal = (0.0, float(np.sin(tilt)), float(np.cos(tilt)))
    result = lofted(plane(0.0), plane(18.0, normal))
    check = check_solid(result.solid.shape)
    assert check.valid
    # Symmetric about the tilt axis: on average 18 mm high.
    assert check.volume == pytest.approx(AREA * 18.0, rel=5e-4)
    assert abs(cap_normal(result.solid.end_cap) @ np.asarray(normal)) == pytest.approx(
        1.0, abs=1e-9
    )
    assert outline_distance(wall_points(result.solid.lateral[0])).max() < 0.02


def test_a_plane_along_the_axis_is_not_reached() -> None:
    with pytest.raises(KernelError) as raised:
        lofted(None, PlaneEnd(np.array([0.0, 20.0, 0.0]), np.array([0.0, 1.0, 0.0])))
    assert raised.value.code == ErrorCode.PLANE_NOT_REACHED


def test_a_plane_that_cuts_off_the_range() -> None:
    with pytest.raises(KernelError) as raised:
        lofted(None, plane(3.5))
    assert raised.value.code == ErrorCode.PLANE_CUTS_RANGE
