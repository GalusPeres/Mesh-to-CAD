"""Solid operations against exact volumes, and face tags through booleans and fillets."""

from __future__ import annotations

import math

import numpy as np
import pytest

from m2c_kernel.cad.booleans import boolean, snap_to_target
from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.edges import edges_between, resolve_edge
from m2c_kernel.cad.fillet import fillet_edges
from m2c_kernel.cad.profiles import Profile, profile_edges
from m2c_kernel.cad.solids import (
    cone,
    cylinder,
    extrude,
    extrude_to_plane,
    revolve,
    sphere,
    torus,
)
from m2c_kernel.cad.tags import UNTAGGED, point_on_face
from m2c_kernel.cad.trim import trim_by_face, trim_by_plane
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.errors import KernelError
from tests.cad.profiles import (
    XY,
    XZ,
    named,
    rectangle,
    rectangle_profile,
    rectangle_with_hole,
    ring_profile,
)

pytestmark = pytest.mark.occt

Z = np.array([0.0, 0.0, 1.0])
EXACT = 1e-3  # mm^3


def _box(tag: str = "f1", dx: float = 30.0, dy: float = 20.0, dz: float = 10.0) -> Body:
    return extrude([rectangle_profile(0, 0, dx, dy)], Z, dz, 0.0, tag)


def _top_edges(body: Body, tag: str = "f1") -> list[object]:
    point = (0.0, 0.0, 0.0)
    return [resolve_edge(body, (f"{tag}:cap:end", f"{tag}:side:e{k}"), point, k) for k in range(4)]


def _volume(body: Body) -> float:
    return check_solid(body.shape).volume


# --- Extrude and revolve ---------------------------------------------------------------------


def test_box_has_the_exact_volume_and_one_tag_per_face() -> None:
    body = _box()
    assert _volume(body) == pytest.approx(6000.0, abs=EXACT)
    assert sorted(body.face_tags) == sorted(
        ["f1:cap:start", "f1:cap:end", "f1:side:e0", "f1:side:e1", "f1:side:e2", "f1:side:e3"]
    )


def test_extrude_both_directions_is_exact() -> None:
    body = extrude([rectangle_profile(0, 0, 40, 20)], Z, 10.0, 5.0, "f2")
    assert check_solid(body.shape).is_usable
    assert _volume(body) == pytest.approx(12000.0, abs=EXACT)


def test_side_tags_follow_the_profile_edges() -> None:
    body = _box()
    # Edge e0 runs along y = 0, so its side face is the plane y = 0.
    side = body.face_tags.index("f1:side:e0")
    from m2c_kernel.cad.tags import faces_of

    point = point_on_face(faces_of(body.shape).FindKey(side + 1))
    assert point[1] == pytest.approx(0.0, abs=1e-9)


def test_profile_with_a_hole_keeps_the_hole() -> None:
    body = extrude([named(rectangle_with_hole())], Z, 10.0, 0.0, "f1")
    assert _volume(body) == pytest.approx((800 - 100) * 10, abs=EXACT)
    assert len(body.face_tags) == 10
    assert UNTAGGED not in body.face_tags


def test_zero_length_is_rejected() -> None:
    with pytest.raises(KernelError) as failure:
        extrude([rectangle_profile(0, 0, 4, 4)], Z, 0.0, 0.0, "f1")
    assert failure.value.code == "cad.zeroLength"


def test_extrude_up_to_a_tilted_plane() -> None:
    # Plane through (0, 0, 7) tilted about X: z = 7 + 0.2 * y over the 10 x 10 profile.
    normal = np.array([0.0, -0.2, 1.0])
    body = extrude_to_plane(
        [rectangle_profile(0, 0, 10, 10)], Z, np.array([0, 0, 7.0]), normal, "f3"
    )
    assert _volume(body) == pytest.approx(10 * 10 * (7 + 0.2 * 5), abs=EXACT)
    assert body.face_tags.count("f3:cap:end") == 1
    assert UNTAGGED not in body.face_tags


def test_extrude_up_to_a_plane_behind_or_parallel_fails() -> None:
    profile = [rectangle_profile(0, 0, 10, 10)]
    with pytest.raises(KernelError) as behind:
        extrude_to_plane(profile, Z, np.array([0, 0, -7.0]), Z, "f3")
    assert behind.value.code == "cad.planeBehind"
    with pytest.raises(KernelError) as parallel:
        extrude_to_plane(profile, Z, np.array([0, 0, 7.0]), np.array([1.0, 0, 0]), "f3")
    assert parallel.value.code == "cad.planeParallel"


def test_revolve_tube_and_quarter() -> None:
    profile = ring_profile()
    full = revolve([profile], XZ, np.zeros(3), Z, 360.0, "f4")
    assert _volume(full) == pytest.approx(28274.334, abs=EXACT)
    assert all(tag.startswith("f4:rev:") for tag in full.face_tags)
    quarter = revolve([profile], XZ, np.zeros(3), Z, 90.0, "f4")
    assert _volume(quarter) == pytest.approx(28274.334 / 4, abs=EXACT)
    assert {"f4:cap:start", "f4:cap:end"} <= set(quarter.face_tags)
    assert UNTAGGED not in quarter.face_tags


def test_revolve_names_every_swept_face_after_its_edge() -> None:
    body = revolve([ring_profile()], XZ, np.zeros(3), Z, 360.0, "f4")
    assert sorted(body.face_tags) == ["f4:rev:e0", "f4:rev:e1", "f4:rev:e2", "f4:rev:e3"]


def test_revolve_rejects_an_axis_through_the_profile() -> None:
    profile = rectangle_profile(-5, 0, 10, 10, frame=XZ)
    with pytest.raises(KernelError) as failure:
        revolve([profile], XZ, np.zeros(3), Z, 360.0, "f4")
    assert failure.value.code == "cad.axisCrossesProfile"


def test_revolve_projects_a_nearly_planar_axis_and_rejects_a_skew_one() -> None:
    slightly_off = np.array([0.0, 0.01, 0.0])  # 0.01 mm in front of the sketch plane
    body = revolve([ring_profile()], XZ, slightly_off, Z, 360.0, "f4")
    assert _volume(body) == pytest.approx(28274.334, abs=EXACT)
    with pytest.raises(KernelError) as failure:
        revolve([ring_profile()], XZ, np.zeros(3), np.array([0.0, 0.1, 1.0]), 360.0, "f4")
    assert failure.value.code == "cad.axisNotInPlane"


# --- Primitives --------------------------------------------------------------------------------


def test_primitives_are_exact() -> None:
    axis = np.array([1.0, 1.0, 1.0]) / math.sqrt(3)
    cyl = cylinder(np.zeros(3), axis, 5.0, 20.0, "f5")
    assert _volume(cyl) == pytest.approx(math.pi * 25 * 20, abs=EXACT)
    assert sorted(cyl.face_tags) == ["f5:cap:end", "f5:cap:start", "f5:surface"]
    frustum = cone(np.zeros(3), axis, 10.0, 5.0, 10.0, "f5")
    assert _volume(frustum) == pytest.approx(math.pi * 10 / 3 * (100 + 50 + 25), abs=EXACT)
    pointed = cone(np.zeros(3), axis, 0.0, 6.0, 9.0, "f5")
    assert _volume(pointed) == pytest.approx(math.pi * 36 * 9 / 3, abs=EXACT)
    ball = sphere(np.array([1.0, 2, 3]), 7.0, "f5")
    assert _volume(ball) == pytest.approx(4 / 3 * math.pi * 343, abs=EXACT)
    ring = torus(np.zeros(3), axis, 20.0, 3.0, "f5")
    assert _volume(ring) == pytest.approx(2 * math.pi**2 * 20 * 9, abs=EXACT)


def test_cylinder_caps_are_named_by_their_end() -> None:
    body = cylinder(np.array([0, 0, 5.0]), Z, 3.0, 10.0, "f5")
    from m2c_kernel.cad.tags import faces_of

    faces = faces_of(body.shape)
    heights = {
        tag: point_on_face(faces.FindKey(index + 1))[2] for index, tag in enumerate(body.face_tags)
    }
    assert heights["f5:cap:start"] == pytest.approx(5.0)
    assert heights["f5:cap:end"] == pytest.approx(15.0)


# --- Fillets and chamfers ----------------------------------------------------------------------


def test_fillet_and_chamfer_on_four_top_edges() -> None:
    body = _box()
    rounded = fillet_edges(body, _top_edges(body), 2.0, "fillet", "f6")
    assert _volume(rounded) == pytest.approx(5917.227, abs=EXACT)
    assert sum(tag.startswith("f6:fillet:") for tag in rounded.face_tags) == 4
    assert UNTAGGED not in rounded.face_tags
    bevelled = fillet_edges(body, _top_edges(body), 1.5, "chamfer", "f6")
    assert _volume(bevelled) == pytest.approx(5892.0, abs=EXACT)
    assert sum(tag.startswith("f6:chamfer:") for tag in bevelled.face_tags) == 4


def test_too_large_fillet_fails_with_a_code() -> None:
    body = _box()
    with pytest.raises(KernelError) as failure:
        fillet_edges(body, _top_edges(body), 12.0, "fillet", "f6")
    assert failure.value.code == "cad.filletFailed"
    assert failure.value.params["size"] == 12.0


def test_missing_edge_reports_its_index() -> None:
    with pytest.raises(KernelError) as failure:
        resolve_edge(_box(), ("f1:cap:end", "f9:side:e0"), (0.0, 0.0, 0.0), 3)
    assert failure.value.code == "cad.edgeNotFound"
    assert failure.value.params == {"index": 3}


# --- Trim --------------------------------------------------------------------------------------


def test_tilted_plane_trim_of_a_sphere() -> None:
    ball = sphere(np.zeros(3), 10.0, "f7")
    kept = trim_by_plane(ball, np.array([0, 0, 4.0]), np.array([0, 0.2, 1.0]), "front", "f8")
    assert _volume(kept.body) == pytest.approx(925.353, abs=EXACT)
    assert set(kept.body.face_tags) == {"f8:split", "f7:surface"}
    rest = trim_by_plane(ball, np.array([0, 0, 4.0]), np.array([0, 0.2, 1.0]), "back", "f8")
    assert _volume(rest.body) + 925.353 == pytest.approx(4 / 3 * math.pi * 1000, abs=EXACT)


def test_trim_plane_that_misses_the_body_is_an_error() -> None:
    for keep in ("front", "back"):
        with pytest.raises(KernelError) as failure:
            trim_by_plane(_box(), np.array([0, 0, 50.0]), Z, keep, "f8")
        assert failure.value.code == "cad.toolMissesBody"


def _parabolic_patch() -> object:
    """B-spline face z = 10 + 0.01 x^2 over [-25, 25]^2 (exactly representable)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.collections import Array2_gp_Pnt
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.gp import gp_Pnt

    count = 11
    grid = Array2_gp_Pnt(1, count, 1, count)
    values = np.linspace(-25.0, 25.0, count)
    for i, x in enumerate(values):
        for j, y in enumerate(values):
            grid.SetValue(i + 1, j + 1, gp_Pnt(x, y, 10 + 0.01 * x * x))
    surface = GeomAPI_PointsToBSplineSurface(grid, 3, 3).Surface()
    return BRepBuilderAPI_MakeFace(surface, 1e-6).Face()


def test_patch_trim_keeps_the_chosen_side() -> None:
    block = extrude([rectangle_profile(-20, -20, 40, 40)], Z, 20.0, 0.0, "f1")
    below = trim_by_face(block, _parabolic_patch(), "back", "f9")
    expected_below = 40 * (10 * 40 + 0.01 * 2 * 20**3 / 3)
    assert check_solid(below.shape).is_usable
    assert _volume(below) == pytest.approx(expected_below, rel=1e-5)
    assert "f9:split" in below.face_tags and "f1:cap:start" in below.face_tags
    assert "f1:cap:end" not in below.face_tags
    above = trim_by_face(block, _parabolic_patch(), "front", "f9")
    assert _volume(above) == pytest.approx(40 * 40 * 20 - expected_below, rel=1e-5)


def test_patch_that_misses_the_body_is_an_error() -> None:
    low = extrude([rectangle_profile(-5, -5, 10, 10)], Z, 5.0, 0.0, "f1")
    with pytest.raises(KernelError) as failure:
        trim_by_face(low, _parabolic_patch(), "back", "f9")
    assert failure.value.code == "cad.toolMissesBody"


# --- Booleans ----------------------------------------------------------------------------------


def test_fuse_of_near_coincident_boxes_is_valid() -> None:
    a = _box("fa", 20, 20, 10)
    # Bottom 1e-6 above, top 1e-6 below A's: no single translation snaps both.
    b = extrude([rectangle_profile(10, 5, 20, 10)], Z, 10.0 - 1e-6, -1e-6, "fb")
    fused = boolean("add", a, [b])
    check = check_solid(fused.body.shape)
    assert check.is_usable
    assert check.volume == pytest.approx(20 * 20 * 10 + 10 * 10 * 10, abs=1e-2)


def test_near_coincident_tool_is_snapped_onto_the_target() -> None:
    a = _box("fa", 20, 20, 10)
    b = extrude([rectangle_profile(10, 5, 20, 10)], Z, 10.0 + 3e-4, -3e-4, "fb")  # 0.3 um high
    snapped = snap_to_target(a, b)
    assert _volume(snapped) == pytest.approx(_volume(b))
    fused = boolean("add", a, [b])
    assert fused.issues == ()
    assert _volume(fused.body) == pytest.approx(4000 + 1000, abs=1e-6)
    # Clean result: the snapped faces merge into the planar faces of A.
    assert len(fused.body.face_tags) == 10


def test_disjoint_bodies_do_not_unite_and_cut_needs_overlap() -> None:
    a = _box("fa", 5, 5, 5)
    far = extrude([rectangle_profile(50, 50, 5, 5)], Z, 5.0, 0.0, "fb")
    for kind in ("add", "cut", "intersect"):
        with pytest.raises(KernelError) as failure:
            boolean(kind, a, [far])
        assert failure.value.code == "cad.noOverlap"


def test_cut_removing_everything_is_empty() -> None:
    small = _box("fa", 5, 5, 5)
    large = extrude([rectangle_profile(-1, -1, 10, 10)], Z, 7.0, 1.0, "fb")
    with pytest.raises(KernelError) as failure:
        boolean("cut", small, [large])
    assert failure.value.code == "cad.emptyResult"


def test_cut_that_splits_the_body_is_rejected() -> None:
    body = _box("f1", 30, 20, 10)
    wall = extrude([rectangle_profile(12, -1, 6, 22)], Z, 11.0, 1.0, "f2")
    with pytest.raises(KernelError) as failure:
        boolean("cut", body, [wall])
    assert failure.value.code == "cad.multipleSolids"


def test_cut_splitting_a_tagged_face_keeps_the_tag_and_the_point_picks_the_edge() -> None:
    body = _box("f1", 30, 20, 10)
    # A slot across the whole top splits the top cap in two; the long sides get a notch.
    slot = extrude([rectangle_profile(12, -1, 6, 22)], Z, 20.0, -5.0, "f2")
    cut = boolean("cut", body, [slot]).body
    assert _volume(cut) == pytest.approx(6000 - 6 * 20 * 5, abs=EXACT)
    assert cut.face_tags.count("f1:cap:end") == 2
    assert cut.face_tags.count("f1:side:e0") == 1
    assert "f2:cap:start" in cut.face_tags  # slot floor comes from the tool
    front = ("f1:cap:end", "f1:side:e0")  # edge e0 runs along y = 0
    assert len(edges_between(cut, front)) == 2
    left = resolve_edge(cut, front, (2.0, 0.0, 10.0), 0)
    right = resolve_edge(cut, front, (28.0, 0.0, 10.0), 0)
    assert not left.IsSame(right)
    rounded = fillet_edges(cut, [left], 1.0, "fillet", "f3")
    assert check_solid(rounded.shape).is_usable


def test_profile_edges_are_in_wire_order() -> None:
    face = rectangle(0, 0, 4, 2, XY)
    assert len(profile_edges(face)) == 4
    assert Profile(face, ("a", "b", "c", "d")).edge_names[2] == "c"
