"""Pushing a net's open border past planes and bodies (Offset by reference surfaces)."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.cad.cells import PlaneInput, SurfaceInput, split_cells
from m2c_kernel.cad.distance import signed_distance
from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox, gp_Pnt
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


def test_a_band_inside_a_body_is_pushed_out_of_it() -> None:
    box = BRepPrimAPI_MakeBox(gp_Pnt(-30, -20, 0), gp_Pnt(30, 20, 10)).Solid()
    net = band_net(bottom=1.0, top=9.6)
    body = Reference("b1", lambda point: signed_distance(box, point))
    pushed = push_past(net.vertices, net.quads, [body], tolerance=0.5, reach=2.0)
    limits = _limits(net, pushed.vertices)
    assert np.allclose(limits[: net.around, 2], -0.5, atol=1e-6)
    assert np.allclose(limits[net.rows * net.around :, 2], 10.5, atol=1e-6)
    distance, outward = signed_distance(box, np.array([0.0, 0.0, 9.0]))
    assert distance == pytest.approx(-1.0) and np.allclose(outward, [0, 0, 1])
