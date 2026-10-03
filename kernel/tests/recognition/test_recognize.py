"""Whole-part recognition on scan-like meshes of known parts (ground truth from OCCT)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    TopoDS_Shape,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
)
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.recognition.api import Feature, Recognition, recognize
from tests.kernel_process import KernelProcess
from tests.synthetic import write_binary_stl
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

NOISE = 0.02


def _cylinder(x: float, y: float, z: float, diameter: float, height: float) -> TopoDS_Shape:
    axis = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, diameter / 2.0, height).Shape()


def panel_shape() -> TopoDS_Shape:
    """80 x 50 x 6 plate: two D8 x 2 buttons, a D12 x 3 recess with a D5 x 1.5 button in
    it, and two D6 through holes."""
    shape = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 80.0, 50.0, 6.0).Shape()
    for x in (15.0, 30.0):
        shape = BRepAlgoAPI_Fuse(shape, _cylinder(x, 35.0, 6.0, 8.0, 2.0)).Shape()
    shape = BRepAlgoAPI_Cut(shape, _cylinder(55.0, 25.0, 3.0, 12.0, 10.0)).Shape()
    shape = BRepAlgoAPI_Fuse(shape, _cylinder(55.0, 25.0, 3.0, 5.0, 1.5)).Shape()
    for x in (10.0, 70.0):
        shape = BRepAlgoAPI_Cut(shape, _cylinder(x, 10.0, -1.0, 6.0, 10.0)).Shape()
    return shape


@cache
def panel() -> Recognition:
    part = tessellate_part(panel_shape(), max_edge=0.8)
    rng = np.random.default_rng(7)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, NOISE, rng)
    return recognize(noisy, part.faces, NOISE)


def _diameter(feature: Feature) -> float:
    return 2.0 * feature.outline.named()["radius"]


def _top_features(recognition: Recognition) -> list[Feature]:
    top = next(
        i
        for i, plane in enumerate(recognition.planes)
        if plane.normal[2] > 0.99 and abs(plane.origin[2] - 6.0) < 0.1
    )
    return [feature for feature in recognition.features if feature.plane == top]


def test_buttons_are_equal_circles_with_their_height() -> None:
    buttons = [
        f for f in _top_features(panel()) if f.relief.kind == "boss" and f.relief.parent is None
    ]
    assert len(buttons) == 2
    for button in buttons:
        assert button.outline.kind == "circle"
        assert _diameter(button) == pytest.approx(8.0, abs=0.1)
        assert button.relief.height == pytest.approx(2.0, abs=0.1)
        assert button.relief.top == "flat"
    assert _diameter(buttons[0]) == _diameter(buttons[1])


def test_recess_holds_its_own_button() -> None:
    features = list(panel().features)
    recess = next(f for f in features if f.relief.kind == "pocket" and f.relief.top == "flat")
    assert recess.outline.kind == "circle"
    assert _diameter(recess) == pytest.approx(12.0, abs=0.15)
    assert recess.relief.height == pytest.approx(3.0, abs=0.1)
    children = [features[i] for i in recess.relief.children]
    assert len(children) == 1
    inner = children[0]
    assert inner.relief.kind == "boss" and inner.outline.kind == "circle"
    assert _diameter(inner) == pytest.approx(5.0, abs=0.15)
    assert inner.relief.height == pytest.approx(1.5, abs=0.1)


def test_through_holes_are_found_once() -> None:
    holes = [f for f in panel().features if f.relief.top == "through"]
    assert len(holes) == 2
    for hole in holes:
        assert hole.outline.kind == "circle"
        assert _diameter(hole) == pytest.approx(6.0, abs=0.1)
        assert hole.relief.height == pytest.approx(6.0, abs=0.15)


def test_a_cad_export_is_read_like_a_dense_scan() -> None:
    """CAD exports (and decimated scans) model a wall with triangles from foot to top
    and a flat top with a few large ones: the same features, the same sizes."""
    part = tessellate_part(panel_shape(), max_edge=1000.0)
    found = recognize(part.vertices, part.faces, 0.01)
    described = sorted(
        (
            f.relief.kind,
            f.outline.kind,
            round(_diameter(f), 2),
            round(f.relief.height, 2),
            f.relief.top,
            f.relief.parent is not None,
        )
        for f in found.features
    )
    assert described == [
        ("boss", "circle", 5.0, 1.5, "flat", True),
        ("boss", "circle", 8.0, 2.0, "flat", False),
        ("boss", "circle", 8.0, 2.0, "flat", False),
        ("pocket", "circle", 6.0, 6.0, "through", False),
        ("pocket", "circle", 6.0, 6.0, "through", False),
        ("pocket", "circle", 12.0, 3.0, "flat", False),
    ]


def test_recognize_run_through_the_protocol(kernel: KernelProcess, tmp_path: Path) -> None:
    shape = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 60.0, 40.0, 5.0).Shape()
    shape = BRepAlgoAPI_Fuse(shape, _cylinder(20.0, 20.0, 5.0, 8.0, 2.0)).Shape()
    shape = BRepAlgoAPI_Cut(shape, _cylinder(45.0, 20.0, -1.0, 6.0, 10.0)).Shape()
    part = tessellate_part(shape, max_edge=1.0)
    path = write_binary_stl(tmp_path / "plate.stl", part.vertices, part.faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok
    scan_key = kernel.call("doc.get").result["document"]["scan"]["key"]

    answer = kernel.call("recognize.run", {"scanKey": scan_key}, lane="recognize.run:test")
    assert answer.ok, answer.header.get("error")
    result = answer.result
    features = result["features"]
    kinds = sorted((f["kind"], f["shape"], f["top"]) for f in features)
    assert kinds == [("boss", "circle", "flat"), ("pocket", "circle", "through")]
    boss = next(f for f in features if f["kind"] == "boss")
    assert 2 * boss["params"]["radius"] == pytest.approx(8.0, abs=0.1)
    assert boss["height"] == pytest.approx(2.0, abs=0.1)
    offsets = np.frombuffer(answer.buffers[result["outlineOffsets"]["$buf"]], np.uint32)
    assert len(offsets) == 2 * len(features) + 1
