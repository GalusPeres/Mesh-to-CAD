"""Deviation map budget: one million scan points in under 12 s (ARCHITECTURE.md 1.5)."""

from __future__ import annotations

import time

import numpy as np
import pytest
import trimesh

from m2c_kernel.document.results import Body
from m2c_kernel.inspection.api import BodyInput, reference_for, signed_distances
from tests.inspection.scene import SIGMA, _block_shape

pytestmark = [pytest.mark.occt, pytest.mark.slow]


def test_one_million_points_in_under_12_seconds() -> None:
    fine = reference_for([BodyInput("f1", "sampling", Body(_block_shape()))], 0.02)
    mesh = trimesh.Trimesh(
        fine.triangles.reshape(-1, 3), np.arange(3 * len(fine.faces)).reshape(-1, 3)
    )
    points, triangles = trimesh.sample.sample_surface(mesh, 1_000_000, seed=9)
    rng = np.random.default_rng(9)
    points = points + fine.face_normals[triangles] * rng.normal(0, SIGMA, (len(points), 1))

    start = time.perf_counter()
    reference = reference_for([BodyInput("f1", "timed", Body(_block_shape()))], 0.1)
    result = signed_distances(points, reference, max_distance=2.0)
    elapsed = time.perf_counter() - start

    assert np.isfinite(result.distances).all()
    assert float(np.std(result.distances)) == pytest.approx(SIGMA, abs=0.003)
    assert elapsed < 12.0, f"{elapsed:.1f} s"
