"""An auto net's open border laid onto the rim of the triangles it covers."""

from __future__ import annotations

import numpy as np

from m2c_kernel.surfacing.rim import rim_points, snap_border_to_rim
from m2c_kernel.surfacing.subdivision import limit_matrix
from tests.synthetic.nets import band_net


def _wall(height: float = 10.0, around: int = 128, rows: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """Triangles of an elliptic wall (semi-axes 20 and 12) from z 0 to `height`."""
    angles = np.linspace(0, 2 * np.pi, around, endpoint=False)
    heights = np.linspace(0, height, rows + 1)
    vertices = np.array([(20 * np.cos(a), 12 * np.sin(a), z) for z in heights for a in angles])
    faces = []
    for j in range(rows):
        for i in range(around):
            a, b = j * around + i, j * around + (i + 1) % around
            faces += [(a, b, b + around), (a, b + around, a + around)]
    return vertices, np.array(faces, dtype=np.int64)


def test_the_border_lands_on_the_rim_and_notches_close() -> None:
    vertices, faces = _wall()
    net = band_net(bottom=1.5, top=8.5, radius_bottom=20, radius_top=20)
    cage = net.vertices.copy()
    cage[3, 2] += 2.0  # a notch: one border point well short of the rim
    snapped = snap_border_to_rim(cage, net.quads, vertices, faces)
    limits = limit_matrix(net.quads, len(cage)) @ snapped
    bottom, top = slice(0, net.around), slice(net.rows * net.around, None)
    assert np.allclose(limits[bottom, 2], 0.0, atol=1e-6)
    assert np.allclose(limits[top, 2], 10.0, atol=1e-6)
    inner = slice(net.around, net.rows * net.around)
    assert np.array_equal(snapped[inner], cage[inner])


def test_small_holes_are_spanned_and_far_rims_ignored() -> None:
    vertices, faces = _wall(height=30.0, rows=120)
    centres = vertices[faces].mean(axis=1)
    hole = (np.abs(centres[:, 2] - 5) < 1) & (centres[:, 0] > 19.9)
    rim = rim_points(vertices, faces[~hole], min_loop=24.0, step=0.4)
    # Only the two long rims at the bottom and the top, not the small hole.
    assert np.all((np.abs(rim[:, 2]) < 1e-9) | (np.abs(rim[:, 2] - 30) < 1e-9))
    # A rim out of reach (the net ends far below the top at 30) does not pull the border.
    net = band_net(bottom=0.5, top=1.5, rows=1, radius_bottom=20, radius_top=20)
    snapped = snap_border_to_rim(net.vertices, net.quads, vertices, faces[~hole])
    limits = limit_matrix(net.quads, len(net.vertices)) @ snapped
    assert np.allclose(limits[: net.around, 2], 0.0, atol=1e-6)
    assert np.all(limits[net.around :, 2] < 2.0)
