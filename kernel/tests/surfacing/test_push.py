"""Pushing a net's open border past planes and bodies (Offset by reference surfaces)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.cad.cells import PlaneInput, SurfaceInput, split_cells
from m2c_kernel.cad.distance import face_measures
from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox, gp_Pnt
from m2c_kernel.document.results import Body
from m2c_kernel.surfacing.net import net_shape
from m2c_kernel.surfacing.push import Reference, plane_reference, push_past
from m2c_kernel.surfacing.subdivision import limit_matrix
from tests.kernel_process import KernelProcess
from tests.surfacing.test_rim import _wall
from tests.synthetic import write_binary_stl
from tests.synthetic.nets import BandNet, band_net

pytestmark = pytest.mark.occt


def _limits(net: BandNet, vertices: np.ndarray) -> np.ndarray:
    return np.asarray(limit_matrix(net.quads, len(vertices)) @ vertices)


def _planes(net: BandNet, vertices: np.ndarray) -> list[Reference]:
    limits = _limits(net, vertices)
    return [
        plane_reference("p1", np.zeros(3), np.array([0, 0, 1.0]), limits),
        plane_reference("p2", np.array([0, 0, 10.0]), np.array([0, 0, 1.0]), limits),
    ]


def test_a_band_short_of_two_planes_is_pushed_past_both() -> None:
    net = band_net(bottom=0.6, top=9.2)
    pushed = push_past(
        net.vertices, net.quads, _planes(net, net.vertices), tolerance=0.5, reach=2.0
    )
    limits = _limits(net, pushed.vertices)
    bottom, top = slice(0, net.around), slice(net.rows * net.around, None)
    assert np.allclose(limits[bottom, 2], -0.5) and np.allclose(limits[top, 2], 10.5)
    assert pushed.moved == 2 * net.around and pushed.references == ("p1", "p2")
    # Only border control points move; the inner rows keep their place.
    inner = slice(net.around, net.rows * net.around)
    assert np.array_equal(pushed.vertices[inner], net.vertices[inner])
    # Now the planes close the band into one solid.
    shape = net_shape(pushed.vertices, net.quads, lambda: None)
    planes = [PlaneInput(np.array([0, 0, h]), np.array([0, 0, 1.0]), f"p{h}") for h in (0, 10)]
    assert len(split_cells([], [SurfaceInput(shape.shape, "n")], planes, "t")) == 1


def test_points_out_of_reach_and_pinned_points_stay() -> None:
    net = band_net(bottom=0.6, top=7.0)
    fixed = np.zeros(len(net.vertices), dtype=bool)
    fixed[0] = True
    pushed = push_past(
        net.vertices,
        net.quads,
        _planes(net, net.vertices),
        tolerance=0.5,
        reach=2.0,
        fixed=fixed,
    )
    before, after = _limits(net, net.vertices), _limits(net, pushed.vertices)
    top = slice(net.rows * net.around, None)
    # The top border is 3 mm below its plane, out of reach: it stays.
    assert np.allclose(after[top], before[top])
    assert np.allclose(after[0], before[0])
    assert np.allclose(after[1 : net.around, 2], -0.5)
    assert pushed.moved == net.around - 1 and pushed.references == ("p1",)


def _box_faces(box: object, name: str = "b1") -> list[Reference]:
    return [Reference(name, measure) for measure in face_measures(box, 2.0)]


def test_a_band_inside_a_body_is_pushed_out_of_it() -> None:
    box = BRepPrimAPI_MakeBox(gp_Pnt(-30, -20, 0), gp_Pnt(30, 20, 10)).Solid()
    net = band_net(bottom=1.0, top=9.6)
    pushed = push_past(net.vertices, net.quads, _box_faces(box), tolerance=0.5, reach=2.0)
    limits = _limits(net, pushed.vertices)
    assert np.allclose(limits[: net.around, 2], -0.5, atol=1e-6)
    assert np.allclose(limits[net.rows * net.around :, 2], 10.5, atol=1e-6)


def _rounding_net(columns: int = 7) -> BandNet:
    """A net on the rounded back edge of the block (R 6 along x at y = 40, z = 20).

    It starts 2 mm before the rounding on the top (y = 32) and ends 2 mm below it on
    the back (z = 12), and stops 1.5 mm short of the end faces. Row j runs along x.
    """
    angles = np.radians([22.5, 45.0, 67.5])
    profile = [
        (32.0, 20.0),
        (34.0, 20.0),
        *((34.0 + 6.0 * np.sin(a), 14.0 + 6.0 * np.cos(a)) for a in angles),
        (40.0, 14.0),
        (40.0, 12.0),
    ]
    xs = np.linspace(1.5, 58.5, columns)
    vertices = np.array([(x, y, z) for y, z in profile for x in xs])
    quads = [
        (j * columns + i, j * columns + i + 1, (j + 1) * columns + i + 1, (j + 1) * columns + i)
        for j in range(len(profile) - 1)
        for i in range(columns - 1)
    ]
    return BandNet(vertices, np.array(quads, dtype=np.int64), columns, len(profile) - 1)


def test_a_rounding_net_passes_the_faces_it_ends_at() -> None:
    # The net must pass the top and the back where it lies on them, and the end faces
    # it runs into, but not the top and the back beside its ends, which it runs along:
    # there it stays on the rounding (issue #7).
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(60, 40, 20)).Solid()
    net = _rounding_net()
    before = _limits(net, net.vertices)
    pushed = push_past(net.vertices, net.quads, _box_faces(box), tolerance=0.5, reach=2.0)
    limits = _limits(net, pushed.vertices)
    columns, rows = net.around, net.rows
    top, back = slice(0, columns), slice(rows * columns, None)
    assert np.allclose(limits[top, 2], 20.5, atol=1e-6)
    assert np.allclose(limits[back, 1], 40.5, atol=1e-6)
    ends = np.array([j * columns + i for j in range(1, rows) for i in (0, columns - 1)])
    assert np.allclose(np.abs(limits[ends, 0] - 30), 30.5, atol=1e-6)
    # On the arc between the tangent lines the ends only move along x.
    arc = np.array([j * columns + i for j in range(2, rows - 1) for i in (0, columns - 1)])
    assert np.allclose(limits[arc, 1:], before[arc, 1:], atol=1e-6)
    # Net and block now enclose the corner: two pieces.
    shape = net_shape(pushed.vertices, net.quads, lambda: None)
    body = Body(shape=box, face_tags=tuple(f"b:{i}" for i in range(6)))
    assert len(split_cells([body], [SurfaceInput(shape.shape, "n")], [], "t")) == 2


def _buffer(index: int, array: np.ndarray) -> dict[str, object]:
    return {"$buf": index, "dtype": str(array.dtype), "shape": list(array.shape)}


def test_push_through_the_protocol_keeps_the_inner_rows_on_the_scan(
    kernel: KernelProcess, tmp_path: Path
) -> None:
    # An elliptic wall (20 x 12) from z = 0 to 10; a band on it from z = 0.6 is pushed
    # past the XY plane at the wall's foot, then its inner rows are fitted again.
    vertices, faces = _wall()
    path = write_binary_stl(tmp_path / "wall.stl", vertices, faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok
    assert kernel.call("automation.bounds").result["min"][2] == pytest.approx(0.0)
    net = band_net(bottom=0.6, top=4.6, radius_bottom=20, radius_top=20)
    cage, quads = net.vertices.astype(np.float64), net.quads.astype(np.uint32)
    answer = kernel.call(
        "net.pushPast",
        {
            "vertices": _buffer(0, cage),
            "quads": _buffer(1, quads),
            "planes": ["XY"],
            "bodies": [],
        },
        buffers=[cage, quads],
        lane="net.pushPast:test",
        timeout=120,
    )
    assert answer.ok, answer.header.get("error")
    assert answer.result["moved"] == net.around and answer.result["references"] == ["XY"]
    pushed = np.frombuffer(answer.buffers[answer.result["vertices"]["$buf"]], np.float64)
    limits = _limits(net, pushed.reshape(-1, 3))
    assert np.allclose(limits[: net.around, 2], -0.5, atol=1e-6)
    inner = limits[net.around : net.rows * net.around]
    radial = np.hypot(inner[:, 0] / 20.0, inner[:, 1] / 12.0)
    # Without the fit the inner rows stay 2.5 % inside the wall; with it, close to it
    # (the first row bends towards the border held below the wall's foot).
    assert np.all(np.abs(radial - 1.0) < 0.01)
    assert np.all(np.abs(radial[net.around :] - 1.0) < 0.003)
