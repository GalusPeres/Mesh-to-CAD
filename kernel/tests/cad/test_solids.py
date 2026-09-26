"""Solid operations against exact volumes, and face tags through booleans and fillets."""

from __future__ import annotations

import math

import numpy as np
import pytest

from m2c_kernel.cad.booleans import boolean
from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.edges import edges_between, resolve_edge
from m2c_kernel.cad.solids import (
    Profile,
    cone,
    cylinder,
    extrude,
    extrude_to_plane,
    fillet_edges,
    profile_edges,
    revolve,
    sphere,
    torus,
    trim_by_plane,
)
from m2c_kernel.document.results import Body, PlaneFrame
from m2c_kernel.protocol.errors import KernelError
from tests.cad.profiles import XY, XZ, rectangle, rectangle_profile, ring_profile

pytestmark = pytest.mark.occt


def _box(tag: str = "f1", dx: float = 30.0, dy: float = 20.0, dz: float = 10.0) -> Body:
    return extrude([rectangle_profile(0, 0, dx, dy)], np.array([0, 0, 1.0]), dz, 0.0, tag)


def _top_edge_refs(body: Body, tag: str = "f1") -> list[tuple[tuple[str, str], tuple[float, float, float]]]:
    return [((f"{tag}:cap:end", f"{tag}:side:e{k}"), (0.0, 0.0, 0.0)) for k in range(4)]


def test_extrude_both_directions_is_exact() -> None:
    body = extrude([rectangle_profile(0, 0, 40, 20)], np.array([0, 0, 1.0]), 10.0, 5.0, "f2")
    check = check_solid(body.shape)
    assert check.is_usable
    assert check.volume == pytest.approx(12000.0, abs=1e-3)
    assert sorted(body.face_tags) == sorted(
        ["f2:cap:start", "f2:cap:end", "f2:side:e0", "f2:side:e1", "f2:side:e2", "f2:side:e3"]
    )


def test_box_volume_and_side_tags_follow_the_profile_edges() -> None:
    body = _box()
    assert check_solid(body.shape).volume == pytest.approx(6000.0, abs=1e-3)
    assert "untagged" not in body.face_tags


def test_extrude_up_to_a_tilted_plane() -> None:
    normal = np.array([0.0, 0.0, 1.0])
    body = extrude_to_plane(
        [rectangle_profile(0, 0, 10, 10)], normal, np.array([0, 0, 7.0]), normal, "f3"
    )
    assert check_solid(body.shape).volume == pytest.approx(700.0, abs=1e-3)
    assert body.face_tags.count("f3:cap:end") == 1
    with pytest.raises(KernelError) as behind:
        extrude_to_plane(
            [rectangle_profile(0, 0, 10, 10)], normal, np.array([0, 0, -7.0]), normal, "f3"
        )
    assert behind.value.code == "cad.planeBehind"


def test_revolve_tube_and_quarter() -> None:
    profile = ring_profile()
    axis_point, axis = np.zeros(3), np.array([0.0, 0.0, 1.0])
    full = revolve([profile], XZ, axis_point, axis, 360.0, "f4")
    assert check_solid(full.shape).volume == pytest.approx(28274.334, abs=1e-3)
    quarter = revolve([profile], XZ, axis_point, axis, 90.0, "f4")
    assert check_solid(quarter.shape).volume == pytest.approx(28274.334 / 4, abs=1e-3)
    assert {"f4:cap:start", "f4:cap:end"} <= set(quarter.face_tags)
    assert all(tag.startswith("f4:rev:") for tag in full.face_tags)


def test_revolve_rejects_an_axis_through_the_profile() -> None:
    profile = rectangle_profile(-5, 0, 10, 10, frame=XZ)
    with pytest.raises(KernelError) as failure:
        revolve([profile], XZ, np.zeros(3), np.array([0.0, 0.0, 1.0]), 360.0, "f4")
    assert failure.value.code == "cad.axisCrossesProfile"


def test_primitives_are_exact() -> None:
    axis = np.array([1.0, 1.0, 1.0]) / math.sqrt(3)
    cyl = cylinder(np.zeros(3), axis, 5.0, 20.0, "f5")
    assert check_solid(cyl.shape).volume == pytest.approx(math.pi * 25 * 20, abs=1e-3)
    assert sorted(cyl.face_tags) == ["f5:cap:end", "f5:cap:start", "f5:lateral"]
    frustum = cone(np.zeros(3), axis, 10.0, 5.0, 10.0, "f5")
    expected = math.pi * 10 / 3 * (100 + 50 + 25)
    assert check_solid(frustum.shape).volume == pytest.approx(expected, abs=1e-3)
    ball = sphere(np.array([1.0, 2, 3]), 7.0, "f5")
    assert check_solid(ball.shape).volume == pytest.approx(4 / 3 * math.pi * 343, abs=1e-3)
    ring = torus(np.zeros(3), axis, 20.0, 3.0, "f5")
    assert check_solid(ring.shape).volume == pytest.approx(2 * math.pi**2 * 20 * 9, abs=1e-3)


def test_fillet_and_chamfer_on_four_top_edges() -> None:
    body = _box()
    edges = [resolve_edge(body, faces, point, i) for i, (faces, point) in enumerate(_top_edge_refs(body))]
    rounded = fillet_edges(body, edges, 2.0, chamfer=False, tag="f6")
    assert check_solid(rounded.shape).volume == pytest.approx(5917.227, abs=1e-3)
    assert sum(tag.startswith("f6:fillet:") for tag in rounded.face_tags) == 4
    assert "untagged" not in rounded.face_tags
    bevelled = fillet_edges(body, edges, 1.5, chamfer=True, tag="f6")
    assert check_solid(bevelled.shape).volume == pytest.approx(5892.0, abs=1e-3)


def test_too_large_fillet_fails_with_a_code() -> None:
    body = _box()
    edges = [resolve_edge(body, faces, point, i) for i, (faces, point) in enumerate(_top_edge_refs(body))]
    with pytest.raises(KernelError) as failure:
        fillet_edges(body, edges, 12.0, chamfer=False, tag="f6")
    assert failure.value.code == "cad.filletFailed"


def test_missing_edge_reports_its_index() -> None:
    with pytest.raises(KernelError) as failure:
        resolve_edge(_box(), ("f1:cap:end", "f9:side:e0"), (0.0, 0.0, 0.0), 3)
    assert failure.value.code == "cad.edgeNotFound"
    assert failure.value.params == {"index": 3}


def test_tilted_plane_trim_of_a_sphere() -> None:
    ball = sphere(np.zeros(3), 10.0, "f7")
    kept, _issues = trim_by_plane(ball, np.array([0, 0, 4.0]), np.array([0, 0.2, 1.0]), "front", "f8")
    assert check_solid(kept.shape).volume == pytest.approx(925.353, abs=1e-3)
    assert "f8:cut" in kept.face_tags and "f7:surface" in kept.face_tags


def test_fuse_of_near_coincident_boxes_is_valid() -> None:
    a = _box("fa", 20, 20, 10)
    b = extrude([rectangle_profile(10, 5, 20, 10)], np.array([0, 0, 1.0]), 10.0 + 2e-6, -1e-6, "fb")
    fused = boolean("add", a, [b])
    check = check_solid(fused.body.shape)
    assert check.is_usable
    assert check.volume == pytest.approx(20 * 20 * 10 + 10 * 10 * 10, abs=1e-2)


def test_cut_splitting_a_tagged_face_keeps_the_tag_and_the_point_picks_the_edge() -> None:
    body = _box("f1", 30, 20, 10)
    # A slot across the whole top splits the top cap and the long sides into two pieces.
    slot = extrude([rectangle_profile(12, -1, 6, 22)], np.array([0, 0, 1.0]), 20.0, -5.0, "f2")
    cut = boolean("cut", body, [slot]).body
    assert check_solid(cut.shape).volume == pytest.approx(6000 - 6 * 20 * 5, abs=1e-3)
    assert cut.face_tags.count("f1:cap:end") == 2
    front = ("f1:cap:end", "f1:side:e0")  # edge e0 runs along y = 0
    candidates = edges_between(cut, front)
    assert len(candidates) == 2
    left = resolve_edge(cut, front, (2.0, 0.0, 10.0), 0)
    right = resolve_edge(cut, front, (28.0, 0.0, 10.0), 0)
    assert not left.IsSame(right)
    rounded = fillet_edges(cut, [left], 1.0, chamfer=False, tag="f3")
    assert check_solid(rounded.shape).is_usable


def test_empty_cut_is_an_error() -> None:
    with pytest.raises(KernelError) as failure:
        boolean("intersect", _box("fa", 5, 5, 5), [extrude([rectangle_profile(50, 50, 5, 5)], np.array([0, 0, 1.0]), 5.0, 0.0, "fb")])
    assert failure.value.code == "cad.emptyResult"


def test_profile_edges_are_stable() -> None:
    face = rectangle(0, 0, 4, 2, XY)
    assert len(profile_edges(face)) == 4
    assert isinstance(Profile(face, ("a",)).edge_names, tuple)
    assert isinstance(XY, PlaneFrame)
