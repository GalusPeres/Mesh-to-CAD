"""Lofts keep the corners of the outline: a block with tight vertical roundings.

With 96 points per section (3.5 mm apart around this outline) the loft cut the
2.8 mm corners by 0.14 mm, and every section had knots of its own.
"""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GeomAbs import GeomAbs_Line
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from m2c_kernel.cad.check import check_solid
from m2c_kernel.freeform.loft import LoftAxis, ScanLoft, loft_scan, section_points
from tests.freeform.shapes import FloatArray, IntArray, tube_scan
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

Z = np.array([0.0, 0.0, 1.0])
SIZE = (50.0, 118.0, 20.0)
"""About the remote control's outline."""
CORNER_MM = 2.8


@cache
def block() -> tuple[FloatArray, IntArray]:
    """A block centred on the Z axis with its vertical edges rounded by CORNER_MM."""
    shape = BRepPrimAPI_MakeBox(gp_Pnt(-SIZE[0] / 2, -SIZE[1] / 2, 0.0), *SIZE).Shape()
    fillet = BRepFilletAPI_MakeFillet(shape)
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.99:
            fillet.Add(CORNER_MM, edge)
        explorer.Next()
    part = tessellate_part(fillet.Shape(), 1.0)
    return part.vertices, part.faces


@cache
def loft() -> ScanLoft:
    vertices, faces = block()
    return loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 3.0, 17.0, 12)


def outline_distance(points: FloatArray) -> FloatArray:
    """Distance in XY to the true outline: a rectangle with CORNER_MM corners."""
    inner = np.array([SIZE[0] / 2, SIZE[1] / 2]) - CORNER_MM
    q = np.abs(points[:, :2]) - inner
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(q.max(axis=1), 0.0)
    result: FloatArray = np.abs(outside - CORNER_MM)
    return result


def wall_points(wall: object) -> FloatArray:
    """Nodes of a fine triangulation of the loft's wall."""
    face = TopoDS.Face(wall)
    BRepMesh_IncrementalMesh(face, 0.002, False, 0.05, True)
    triangulation = BRep_Tool.Triangulation_s(face, TopLoc_Location())
    nodes = [triangulation.Node(i) for i in range(1, triangulation.NbNodes() + 1)]
    return np.array([[node.X(), node.Y(), node.Z()] for node in nodes])


def test_the_section_count_follows_the_outline() -> None:
    vertices, faces = block()
    # 336 mm around: one point every 0.5 mm, rounded up to 96 times a power of two.
    assert section_points(vertices, faces, Z) == 768
    assert len(loft().sections[0]) == 768


def test_the_wall_keeps_the_corners_everywhere() -> None:
    result = loft()
    assert check_solid(result.solid.shape).valid
    points = wall_points(result.solid.lateral[0])
    corners = np.all(np.abs(points[:, :2]) > np.array(SIZE[:2]) / 2 - CORNER_MM, axis=1)
    assert corners.sum() > 500
    assert outline_distance(points).max() < 0.02
    assert result.section_max < 0.02


def test_all_sections_share_one_knot_vector() -> None:
    # The tube's sections change along the height, so chord-length parameters differ.
    vertices, faces = tube_scan(sigma=0.02)
    result = loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 5.0, 55.0, 8)
    surface = BRepAdaptor_Surface(TopoDS.Face(result.solid.lateral[0])).BSpline()
    # A periodic section of n points has n poles (n + 3 once ThruSections opens it).
    assert surface.NbUPoles() <= len(result.sections[0]) + 3
