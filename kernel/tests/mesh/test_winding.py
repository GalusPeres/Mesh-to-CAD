"""Inside or outside a scan by the generalised winding number."""

from __future__ import annotations

import numpy as np

from m2c_kernel.mesh.winding import winding_numbers
from tests.synthetic import sphere_scan


def test_inside_is_one_and_outside_zero_also_with_a_hole() -> None:
    vertices, faces = sphere_scan(radius=20.0, subdivisions=3)
    points = np.array([[0, 0, 0], [0, 0, 19.0], [0, 0, 21.0], [50, 0, 0]], dtype=np.float64)
    assert np.allclose(winding_numbers(vertices, faces, points), [1, 1, 0, 0], atol=1e-6)
    # An open bottom (as on many scans): points well inside still count as inside.
    centroids = vertices[faces].mean(axis=1)
    open_bottom = faces[centroids[:, 2] > -18.0]
    inside, outside = winding_numbers(vertices, open_bottom, points[[0, 3]])
    assert inside > 0.9 and abs(outside) < 0.05
    # A scan with inward normals counts the other way round.
    assert np.isclose(winding_numbers(vertices, faces[:, ::-1], points[:1])[0], -1.0)
