"""Contracts of the shared Open CASCADE helpers: validity checks and display tessellation."""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.occt


def test_check_solid_accepts_a_box() -> None:
    from m2c_kernel.cad.check import check_solid
    from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox

    check = check_solid(BRepPrimAPI_MakeBox(30.0, 20.0, 10.0).Shape())
    assert check.is_usable
    assert check.solids == 1
    assert check.volume == pytest.approx(6000.0)
    assert check.area == pytest.approx(2 * (600 + 300 + 200))
    assert not check.high_tolerance


def test_check_solid_rejects_a_face() -> None:
    from m2c_kernel.cad.check import check_solid
    from m2c_kernel.cad.occ_compat import BRepBuilderAPI_MakeFace, gp_Pln

    face = BRepBuilderAPI_MakeFace(gp_Pln(), 0.0, 1.0, 0.0, 1.0).Face()
    assert not check_solid(face).is_usable


def test_tessellation_is_watertight_and_outward() -> None:
    import trimesh

    from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeCylinder, gp_Ax2, gp_Dir, gp_Pnt
    from m2c_kernel.cad.tessellate import tessellate

    shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 8.0, 20.0).Shape()
    mesh = tessellate(shape)
    assert set(np.unique(mesh.triangle_faces)) == {0, 1, 2}
    assert len(mesh.edge_segments) == len(mesh.segment_edges) > 0
    merged = trimesh.Trimesh(mesh.vertices, mesh.triangles, process=True)
    assert merged.is_watertight
    assert merged.volume == pytest.approx(np.pi * 64 * 20, rel=0.01)


def test_occt_version_is_readable() -> None:
    from m2c_kernel.cad.occ_compat import occt_version

    assert occt_version().startswith("8.")


def test_edge_segments_know_their_faces() -> None:
    from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox
    from m2c_kernel.cad.tessellate import tessellate

    mesh = tessellate(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape())
    assert mesh.segment_faces.shape == (len(mesh.edge_segments), 2)
    # Every edge of a box separates two different faces.
    assert (mesh.segment_faces[:, 0] != mesh.segment_faces[:, 1]).all()
    assert mesh.segment_faces.max() == 5
