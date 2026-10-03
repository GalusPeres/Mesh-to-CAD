"""Pushing a net's open border past planes and bodies (Offset by reference surfaces)."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.cad.cells import PlaneInput, SurfaceInput, split_cells
from m2c_kernel.cad.distance import face_measures
from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox, gp_Pnt
from m2c_kernel.document.results import Body
from m2c_kernel.surfacing.net import net_shape
from m2c_kernel.surfacing.push import Reference, plane_reference, push_past
from m2c_kernel.surfacing.subdivision import limit_matrix
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


def _sheet(x: tuple[float, float], y: tuple[float, float], z: float, cells: int = 4) -> BandNet:
    """A flat grid of cells x cells quads at height z, facing up."""
    xs, ys = np.linspace(*x, cells + 1), np.linspace(*y, cells + 1)
    vertices = np.array([(px, py, z) for py in ys for px in xs])
    quads = [
        (
            j * (cells + 1) + i,
            j * (cells + 1) + i + 1,
            (j + 1) * (cells + 1) + i + 1,
            (j + 1) * (cells + 1) + i,
        )
        for j in range(cells)
        for i in range(cells)
    ]
    return BandNet(vertices, np.array(quads, dtype=np.int64), cells + 1, cells)


def test_a_border_passes_every_face_near_it_not_only_the_nearest() -> None:
    # The sheet lies 1 mm under the top of the block and 1.5 mm short of its end faces:
    # its border must pass the top and, at the ends, the end faces too, or it encloses
    # nothing with the block (a rounding net along a block's edge, issue #7).
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(60, 40, 20)).Solid()
    net = _sheet((1.5, 58.5), (10.0, 30.0), 19.0)
    pushed = push_past(net.vertices, net.quads, _box_faces(box), tolerance=0.5, reach=2.0)
    limits = _limits(net, pushed.vertices)
    border = np.unique(
        np.concatenate(
            [
                np.flatnonzero(np.isclose(net.vertices[:, k], v))
                for k, v in ((0, 1.5), (0, 58.5), (1, 10), (1, 30))
            ]
        )
    )
    assert np.allclose(limits[border, 2], 20.5, atol=1e-6)
    ends = np.isclose(net.vertices[:, 0], 1.5) | np.isclose(net.vertices[:, 0], 58.5)
    assert np.allclose(np.abs(limits[ends, 0] - 30), 30.5, atol=1e-6)
    shape = net_shape(pushed.vertices, net.quads, lambda: None)
    body = Body(shape=box, face_tags=tuple(f"b:{i}" for i in range(6)))
    assert len(split_cells([body], [SurfaceInput(shape.shape, "n")], [], "t")) == 2
