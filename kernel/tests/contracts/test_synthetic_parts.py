"""OCCT-built test parts that segmentation, fitting, sketch and deviation tests score against."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Sphere, Torus
from tests.synthetic.parts import block_part, plate_part

pytestmark = pytest.mark.occt


def test_block_has_sixteen_known_faces() -> None:
    part = block_part(2.0)
    kinds = [type(surface) for surface in part.surfaces]
    assert len(kinds) == 16
    assert kinds.count(Plane) == 7
    assert kinds.count(Cylinder) == 6
    assert (kinds.count(Cone), kinds.count(Sphere), kinds.count(Torus)) == (1, 1, 1)
    assert set(np.unique(part.labels)) == set(range(16))


def test_triangles_lie_on_their_true_surfaces() -> None:
    part = block_part(2.0)
    centroids = part.vertices[part.faces].mean(axis=1)
    assert np.abs(part.distance_to_truth(centroids)).max() < 0.01


def test_points_outside_the_material_have_positive_distance() -> None:
    part = block_part(2.0)
    above_top = np.array([[10.0, 50.0, 20.5]])
    assert part.distance_to_truth(above_top)[0] == pytest.approx(0.5, abs=1e-6)


def test_plate_holes_and_fillets() -> None:
    radii = sorted(
        round(surface.radius, 6)
        for surface in plate_part(2.0).surfaces
        if isinstance(surface, Cylinder)
    )
    assert radii == [6.0, 6.0, 8.0, 8.0, 8.0, 10.0]
