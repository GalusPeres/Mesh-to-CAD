"""Corners stay on the same section points: a block that widens, with 0.5 mm corners.

Its outline grows by 12 mm around over its height, so evenly spaced points drift along
it from section to section, and a loft through them dented the corners between the
sections (#29). With anchored corners the wall stays on the true surface between the
sections, not only at them.
"""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment
from OCP.gp import gp_Pnt
from OCP.TopoDS import TopoDS

from m2c_kernel.cad.check import check_solid
from m2c_kernel.freeform.anchors import corners
from m2c_kernel.freeform.loft import LoftAxis, ScanLoft, loft_scan
from m2c_kernel.freeform.sections import largest_loop, outline, section_loops
from tests.freeform.shapes import FloatArray, IntArray
from tests.freeform.test_loft_corners import wall_points
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

Z = np.array([0.0, 0.0, 1.0])
HEIGHT = 20.0
LENGTH = 118.0
CORNER_MM = 0.5


def half_width(z: FloatArray) -> FloatArray:
    """25 mm at the bottom, 28 mm at the top."""
    result: FloatArray = 25.0 + 3.0 * np.asarray(z) / HEIGHT
    return result


def outline_wire(z: float) -> object:
    """A rectangle with CORNER_MM corners at height z, as lines and arcs."""
    a, b, r = float(half_width(z)), LENGTH / 2, CORNER_MM
    wire = BRepBuilderAPI_MakeWire()
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        # Counter-clockwise: the corner at (sx a, sy b), then the side to the next one.
        start = gp_Pnt(sx * a, sy * (b - r), z) if sx * sy > 0 else gp_Pnt(sx * (a - r), sy * b, z)
        middle = gp_Pnt(sx * (a - r + r / np.sqrt(2)), sy * (b - r + r / np.sqrt(2)), z)
        end = gp_Pnt(sx * (a - r), sy * b, z) if sx * sy > 0 else gp_Pnt(sx * a, sy * (b - r), z)
        wire.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(start, middle, end).Value()).Edge())
        nx, ny = (-sx, sy) if sx * sy > 0 else (sx, -sy)
        following = (
            gp_Pnt(nx * (a - r), ny * b, z) if sx * sy > 0 else gp_Pnt(nx * a, ny * (b - r), z)
        )
        wire.Add(BRepBuilderAPI_MakeEdge(GC_MakeSegment(end, following).Value()).Edge())
    return wire.Wire()


@cache
def block() -> tuple[FloatArray, IntArray]:
    maker = BRepOffsetAPI_ThruSections(True, True)
    for z in (0.0, HEIGHT):
        maker.AddWire(TopoDS.Wire(outline_wire(z)))
    maker.Build()
    part = tessellate_part(maker.Shape(), 1.0)
    return part.vertices, part.faces


@cache
def loft() -> ScanLoft:
    vertices, faces = block()
    return loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 3.0, 17.0, 12)


def true_distance(points: FloatArray) -> FloatArray:
    """Distance in XY to the true outline at each point's height."""
    inner = np.column_stack([half_width(points[:, 2]), np.full(len(points), LENGTH / 2)])
    q = np.abs(points[:, :2]) - (inner - CORNER_MM)
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(q.max(axis=1), 0.0)
    result: FloatArray = np.abs(outside - CORNER_MM)
    return result


def test_the_block_has_four_corners_in_every_section() -> None:
    vertices, faces = block()
    for height in (3.0, 10.0, 17.0):
        loop = largest_loop(section_loops(vertices, faces, np.zeros(3), Z, height), Z)
        assert loop is not None
        assert len(corners(outline(loop, Z, np.array([1.0, 0.0, 0.0])), Z)) == 4


def test_corners_stay_on_the_same_points() -> None:
    sections = loft().sections
    for corner in ((1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)):
        at = [int(np.argmax(points[:, :2] @ np.asarray(corner))) for points in sections]
        assert max(at) - min(at) <= 1


def test_the_wall_stays_on_the_true_surface_between_sections() -> None:
    result = loft()
    assert check_solid(result.solid.shape).valid
    points = wall_points(result.solid.lateral[0])
    assert true_distance(points).max() < 0.02
