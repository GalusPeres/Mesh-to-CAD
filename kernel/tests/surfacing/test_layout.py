"""Patch layouts of quad nets and the packed B-Rep built on them."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import BRepCheck_Analyzer
from m2c_kernel.surfacing.layout import PatchLayout, block_sides, patch_layout, side_on_line
from m2c_kernel.surfacing.net import net_deviation, net_shape
from m2c_kernel.surfacing.subdivision import EdgeTopology, edge_topology

pytestmark = pytest.mark.occt

type FloatArray = np.ndarray
type IntArray = np.ndarray


def box_net(size: tuple[int, int, int] = (4, 3, 2)) -> tuple[FloatArray, IntArray]:
    """A box of a x b x c quads per side: eight valence-3 points at the corners."""
    a, b, c = size
    index: dict[tuple[int, int, int], int] = {}
    points: list[tuple[int, int, int]] = []

    def vertex(x: int, y: int, z: int) -> int:
        key = (x, y, z)
        if key not in index:
            index[key] = len(points)
            points.append(key)
        return index[key]

    quads: list[list[int]] = []
    # Each side: fixed axis value and two running axes, oriented outward.
    for axis, value, outward in (
        (0, 0, -1),
        (0, a, 1),
        (1, 0, -1),
        (1, b, 1),
        (2, 0, -1),
        (2, c, 1),
    ):
        others = [k for k in range(3) if k != axis]
        n0, n1 = (size[others[0]], size[others[1]])
        for i in range(n0):
            for j in range(n1):
                corners = []
                for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    p = [0, 0, 0]
                    p[axis], p[others[0]], p[others[1]] = value, i + di, j + dj
                    corners.append(vertex(*p))
                # (others[0], others[1]) is right-handed with +axis for axis 0 and 2 only.
                right_handed = (others[0], others[1], axis) in ((1, 2, 0), (2, 0, 1), (0, 1, 2))
                if (outward > 0) != right_handed:
                    corners.reverse()
                quads.append(corners)
    vertices = np.array(points, dtype=np.float64) * 10.0
    vertices -= vertices.mean(axis=0)
    return vertices, np.array(quads, dtype=np.int64)


def torus_net(rings: int = 12, sides: int = 8) -> tuple[FloatArray, IntArray]:
    """A regular torus grid: no irregular points at all."""
    u = 2 * np.pi * np.arange(rings) / rings
    v = 2 * np.pi * np.arange(sides) / sides
    big, small = 30.0, 10.0
    uu, vv = np.meshgrid(u, v, indexing="ij")
    vertices = np.stack(
        [
            (big + small * np.cos(vv)) * np.cos(uu),
            (big + small * np.cos(vv)) * np.sin(uu),
            small * np.sin(vv),
        ],
        axis=-1,
    ).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(rings), np.arange(sides), indexing="ij")

    def at(di: int, dj: int) -> IntArray:
        result: IntArray = ((i + di) % rings) * sides + (j + dj) % sides
        return result

    quads = np.stack([at(0, 0), at(1, 0), at(1, 1), at(0, 1)], axis=-1).reshape(-1, 4)
    return vertices, quads


def check_layout(layout: PatchLayout, quads: IntArray, topology: EdgeTopology) -> None:
    covered = np.concatenate([block.cells.ravel() for block in layout.blocks])
    assert np.array_equal(np.sort(covered), np.arange(len(quads)))
    valence = np.bincount(topology.edges.ravel(), minlength=topology.n_vertices)
    assert np.all(layout.corners[valence != 4])
    for block in layout.blocks:
        for side in block_sides(block):
            assert (
                side_on_line(side, layout.lines, layout.edge_line, layout.edge_position, topology)
                is not None
            )


def test_box_net_packs_into_its_six_sides() -> None:
    vertices, quads = box_net()
    topology = edge_topology(quads, len(vertices))
    layout = patch_layout(quads, topology)
    check_layout(layout, quads, topology)
    assert len(layout.blocks) == 6
    assert int(layout.corners.sum()) == 8


def test_torus_without_irregular_points_is_split_into_rectangles() -> None:
    vertices, quads = torus_net()
    topology = edge_topology(quads, len(vertices))
    layout = patch_layout(quads, topology)
    check_layout(layout, quads, topology)
    assert 2 <= len(layout.blocks) <= 16
    assert all(block.cells.size > 1 for block in layout.blocks)


@pytest.mark.parametrize("make", [box_net, torus_net])
def test_packed_shape_is_a_valid_solid_with_few_faces(make: object) -> None:
    vertices, quads = make()  # type: ignore[operator]
    shape = net_shape(vertices, quads)
    assert shape.packed and shape.closed
    assert BRepCheck_Analyzer(shape.shape).IsValid()
    assert len(shape.faces) <= 16
    unpacked = net_shape(vertices, quads, packed=False)
    assert not unpacked.packed and len(unpacked.faces) == len(quads)
    # Both describe the same limit surface.
    deviation = net_deviation(shape, unpacked.samples)
    assert deviation is not None and deviation.max < 0.01
