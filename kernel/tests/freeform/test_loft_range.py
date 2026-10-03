"""Where a loft fits: the walls of a body, not a button on top or a flat slope below."""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.GeomAbs import GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from m2c_kernel.cad.check import check_solid
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.loft import LoftAxis, body_range, loft_scan, scan_extent
from m2c_kernel.protocol.errors import KernelError
from tests.freeform.shapes import FloatArray, IntArray
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

Z = LoftAxis(np.zeros(3), np.array([0.0, 0.0, 1.0]))
WIDTH, LENGTH, HEIGHT = 40.0, 80.0, 16.0
SLOPE_HEIGHT = 3.0
"""The back of the bottom rises over the last 10 mm to this height (a flat slope)."""
CORNER = 5.0
"""Radius of the rounded vertical edges, as on a remote (a smooth loft through a section
with sharp corners swings past them)."""


@cache
def remote_like() -> tuple[FloatArray, IntArray]:
    """A block with rounded vertical edges, a flat slope at the back of its bottom and a
    button on its top."""
    profile = BRepBuilderAPI_MakePolygon()
    for y, z in ((0, 0), (LENGTH - 10, 0), (LENGTH, SLOPE_HEIGHT), (LENGTH, HEIGHT), (0, HEIGHT)):
        profile.Add(gp_Pnt(0, y, z))
    profile.Close()
    face = BRepBuilderAPI_MakeFace(profile.Wire()).Face()
    block = BRepPrimAPI_MakePrism(face, gp_Vec(WIDTH, 0, 0)).Shape()
    rounded = BRepFilletAPI_MakeFillet(block)
    edges = TopExp_Explorer(block, TopAbs_EDGE)
    while edges.More():
        edge = TopoDS.Edge(edges.Current())
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.99:
            rounded.Add(CORNER, edge)
        edges.Next()
    block = rounded.Shape()
    button = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(20, 40, HEIGHT), gp_Dir(0, 0, 1)), 3.0, 2.0)
    part = tessellate_part(BRepAlgoAPI_Fuse(block, button.Shape()).Shape(), 1.0)
    return part.vertices, part.faces


def test_the_range_keeps_to_the_walls() -> None:
    vertices, faces = remote_like()
    low, high = scan_extent(vertices, Z)
    start, end = body_range(vertices, faces, Z, low, high)
    assert SLOPE_HEIGHT < start < SLOPE_HEIGHT + 1.0
    assert HEIGHT - 1.0 < end < HEIGHT


def test_a_loft_in_the_range_is_the_block() -> None:
    vertices, faces = remote_like()
    start, end = body_range(vertices, faces, Z, *scan_extent(vertices, Z))
    loft = loft_scan(vertices, faces, Z, start, end, 12)
    check = check_solid(loft.solid.shape)
    exact = (WIDTH * LENGTH - (4.0 - np.pi) * CORNER**2) * (end - start)
    assert check.valid
    # 96 points per section cut a 5 mm corner by a few hundredths of a millimetre.
    assert abs(check.volume - exact) / exact < 1e-2


@pytest.mark.parametrize(("start", "end", "position"), [(1.0, 15.0, 1.0), (4.0, 17.5, 17.5)])
def test_a_loft_into_the_slope_or_the_button_is_refused(
    start: float, end: float, position: float
) -> None:
    vertices, faces = remote_like()
    with pytest.raises(KernelError) as raised:
        loft_scan(vertices, faces, Z, start, end, 12)
    assert raised.value.code == ErrorCode.SECTION_JUMP
    assert raised.value.params["position"] in (pytest.approx(position, abs=1.5),)
