"""Accuracy of the complete selection fit against exact primitives (ARCHITECTURE.md 1.5).

Patches of 40,000 vertices with Gaussian noise (sigma 0.03 mm along the normal),
1 % spikes of 0.15-0.3 mm and a random pose; normals are the jet normals of the
noisy mesh, as in the application. Snapping is off: the free fit is measured.
"""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.fitting.api import Cone, Cylinder, FitRequest, Plane, Sphere, Torus, run_fit
from tests.fitting.helpers import SIGMA, angle_deg, line_distance, noisy_patch

FREE = FitRequest(kind="auto", snap=False)


def _fit(patch_kind: str, span_u: float, span_v: float, seed: int, **shape: float):  # type: ignore[no-untyped-def]
    patch = noisy_patch(patch_kind, span_u, span_v, seed, **shape)
    faces = np.arange(len(patch.faces))
    outcome = run_fit(patch.mesh(), faces, FREE, np.random.default_rng(seed))
    return patch, outcome


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_plane_40_mm_patch(seed: int) -> None:
    patch, outcome = _fit("plane", 40.0, 40.0, seed)
    fit, truth = outcome.primitive, patch.truth
    assert isinstance(fit, Plane) and isinstance(truth, Plane)
    assert angle_deg(fit.normal, truth.normal) < 0.01
    offset = abs(
        float((np.asarray(fit.origin) - np.asarray(truth.origin)) @ np.asarray(truth.normal))
    )
    assert offset < 0.005
    assert outcome.stats.sigma == pytest.approx(SIGMA, rel=0.1)
    assert outcome.stats.passed


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_cylinder_90_degree_arc(seed: int) -> None:
    patch, outcome = _fit("cylinder", np.pi / 2, 40.0, seed, radius=12.5)
    fit, truth = outcome.primitive, patch.truth
    assert isinstance(fit, Cylinder) and isinstance(truth, Cylinder)
    assert angle_deg(fit.axis, truth.axis) < 0.01
    assert abs(fit.radius - 12.5) < 0.01
    assert line_distance(fit.origin, truth.origin, truth.axis) < 0.01
    assert outcome.stats.concave is False


@pytest.mark.parametrize("seed", [1, 2])
def test_cone(seed: int) -> None:
    patch, outcome = _fit("cone", np.pi * 359 / 180, 20.0, seed, half_angle=np.radians(30))
    fit, truth = outcome.primitive, patch.truth
    assert isinstance(fit, Cone) and isinstance(truth, Cone)
    assert angle_deg(fit.axis, truth.axis) < 0.05
    assert np.dot(fit.axis, truth.axis) > 0
    assert abs(np.degrees(fit.half_angle - truth.half_angle)) < 0.05
    assert np.linalg.norm(np.subtract(fit.apex, truth.apex)) < 0.02


@pytest.mark.parametrize("seed", [1, 2])
def test_sphere_cap(seed: int) -> None:
    patch, outcome = _fit("sphere", np.pi / 2, np.pi / 3, seed, radius=20.0)
    fit, truth = outcome.primitive, patch.truth
    assert isinstance(fit, Sphere) and isinstance(truth, Sphere)
    assert abs(fit.radius - 20.0) < 0.02
    assert np.linalg.norm(np.subtract(fit.center, truth.center)) < 0.02


@pytest.mark.parametrize("seed", [1, 2])
def test_torus_fillet(seed: int) -> None:
    patch, outcome = _fit("torus", np.pi / 2, np.pi / 2, seed, major_radius=18.0, minor_radius=3.0)
    fit, truth = outcome.primitive, patch.truth
    assert isinstance(fit, Torus) and isinstance(truth, Torus)
    assert angle_deg(fit.axis, truth.axis) < 0.05
    assert abs(fit.major_radius - 18.0) < 0.02
    assert abs(fit.minor_radius - 3.0) < 0.02
    assert np.linalg.norm(np.subtract(fit.center, truth.center)) < 0.02


def test_statistics_describe_the_residuals() -> None:
    patch, outcome = _fit("cylinder", np.pi, 30.0, 5, radius=10.0)
    stats = outcome.stats
    # The RMS includes the 1 % spikes; the robust sigma recovers the Gaussian noise.
    assert stats.sigma == pytest.approx(SIGMA, rel=0.1)
    assert stats.rms > stats.sigma
    assert 0.15 < stats.max_deviation < 0.4
    assert stats.face_count == len(patch.faces)
    assert stats.point_count == len(patch.vertices)
    assert stats.within_tolerance > 0.95 and stats.passed
    assert stats.uncertainty["radius"] < 0.005
    assert stats.uncertainty["direction"] < 0.01
    assert outcome.alternatives[0].kind == "cylinder"
    assert outcome.alternatives[0].rms == pytest.approx(stats.rms)
