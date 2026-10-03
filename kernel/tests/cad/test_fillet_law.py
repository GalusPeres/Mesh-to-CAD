"""Fillets on lofted end edges, and fillets that narrow where the faces bend tighter."""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.gp import gp_Pnt
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

import m2c_kernel.cad.fillet as fillet_module
from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.edges import edges_between
from m2c_kernel.cad.fillet import fillet_edges
from m2c_kernel.cad.tags import faces_of
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.features.types.loft import tagged_body
from m2c_kernel.freeform.ends import PlaneEnd
from m2c_kernel.freeform.loft import LoftAxis, loft_scan
from m2c_kernel.protocol.errors import KernelError
from tests.freeform.test_loft_anchors import block as cornered_block
from tests.freeform.test_loft_ends import TOP_MM, Z, rounded_block, to_both_planes

pytestmark = pytest.mark.occt


def lofted_block() -> Body:
    return tagged_body(to_both_planes(), "L")


def top_edge(body: Body) -> list[object]:
    return edges_between(body, ("L:cap:end", "L:loft:0"))


def face_points(body: Body, tag: str, count: int = 150) -> np.ndarray:
    faces = faces_of(body.shape)
    points = []
    for index in range(1, faces.Extent() + 1):
        if body.face_tags[index - 1] != tag:
            continue
        face = TopoDS.Face(faces.FindKey(index))
        BRepMesh_IncrementalMesh(face, 0.01, False, 0.1, True)
        mesh = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        points += [mesh.Node(i) for i in range(1, mesh.NbNodes() + 1)]
    chosen = points[:: max(1, len(points) // count)]
    return np.array([[point.X(), point.Y(), point.Z()] for point in chosen])


def distances(points: np.ndarray, shape: object) -> np.ndarray:
    result = []
    for point in points:
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        extrema = BRepExtrema_DistShapeShape(vertex, shape)
        result.append(extrema.Value())
    return np.array(result)


def test_the_lofted_end_edge_takes_the_rounding_of_the_part() -> None:
    body = lofted_block()
    rounded = fillet_edges(body, top_edge(body), TOP_MM, "fillet", "F")
    assert rounded.smallest is None
    truth = rounded_block(TOP_MM)
    check = check_solid(rounded.body.shape)
    assert check.valid and check.solids == 1
    assert check.volume == pytest.approx(check_solid(truth).volume, rel=5e-4)
    assert distances(face_points(rounded.body, "F:fillet:0"), truth).max() < 0.02


@cache
def cornered_loft() -> Body:
    """A lofted block with 0.5 mm vertical corners, from plane z 0 to plane z 20."""
    vertices, faces = cornered_block()
    loft = loft_scan(
        vertices,
        faces,
        LoftAxis(np.zeros(3), Z),
        3.0,
        17.0,
        12,
        start_plane=PlaneEnd(np.zeros(3), Z),
        end_plane=PlaneEnd(np.array([0.0, 0.0, 20.0]), Z),
    )
    return tagged_body(loft, "L")


def test_a_rounding_narrows_where_the_corners_are_tighter() -> None:
    body = cornered_loft()
    rounded = fillet_edges(body, top_edge(body), 0.78, "fillet", "F")
    assert rounded.smallest is not None
    assert 0.0 < rounded.smallest <= 0.5 * 0.5 + 1e-6
    check = check_solid(rounded.body.shape)
    assert check.valid and check.solids == 1 and check.max_tolerance < 1e-3


def test_without_narrowing_the_same_rounding_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fillet_module, "radius_law", lambda *args: None)
    body = cornered_loft()
    with pytest.raises(KernelError) as raised:
        fillet_edges(body, top_edge(body), 0.78, "fillet", "F")
    assert raised.value.code == ErrorCode.FILLET_FAILED


def test_a_loose_result_counts_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fillet_module, "MAX_TOLERANCE_MM", 1e-9)
    body = lofted_block()
    with pytest.raises(KernelError) as raised:
        fillet_edges(body, top_edge(body), TOP_MM, "fillet", "F")
    assert raised.value.code == ErrorCode.FILLET_FAILED
    assert raised.value.details is not None and "tolerance" in raised.value.details
