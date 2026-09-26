"""Robust fitting (LO-RANSAC) of selections that contain other surfaces and junk.

The selection is 55 % the wanted surface, 35 % a wall crossing it and 10 %
random triangles (ARCHITECTURE.md 1.5: axis < 0.05 degrees, radius < 0.01 mm).
"""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.api import Cylinder, FitRequest, Plane, fit_robust, run_fit
from m2c_kernel.geometry import unit
from tests.fitting.helpers import SIGMA, angle_deg, combine, line_distance, noisy_patch
from tests.synthetic.meshes import _grid_faces


def _cluttered(kind: str, seed: int, **shape: float) -> tuple[EvalMesh, int, object]:
    rng = np.random.default_rng(seed + 100)
    span_u, span_v = (40.0, 40.0) if kind == "plane" else (np.radians(120), 30.0)
    patch = noisy_patch(kind, span_u, span_v, seed, resolution=160, **shape)
    centre = patch.vertices.mean(axis=0)
    wall_faces = int(len(patch.faces) * 0.35 / 0.55)
    junk_faces = int(len(patch.faces) * 0.10 / 0.55)

    n = int(np.sqrt(wall_faces / 2)) + 1
    wall_normal = unit(rng.normal(size=3))
    e1 = unit(np.cross(wall_normal, rng.normal(size=3)))
    e2 = np.cross(wall_normal, e1)
    u, v = np.meshgrid(np.linspace(-20, 20, n), np.linspace(-20, 20, n), indexing="ij")
    wall = centre + u.reshape(-1, 1) * e1 + v.reshape(-1, 1) * e2
    wall += wall_normal * rng.normal(0.0, SIGMA, (len(wall), 1))

    corners = (
        centre + rng.uniform(-20, 20, (junk_faces, 1, 3)) + rng.normal(0, 0.4, (junk_faces, 3, 3))
    )
    junk = corners.reshape(-1, 3)
    vertices, faces = combine(
        (patch.vertices, patch.faces),
        (wall, _grid_faces(n, n)),
        (junk, np.arange(len(junk)).reshape(-1, 3)),
    )
    return EvalMesh("mesh:clutter", vertices, faces, None), len(patch.faces), patch.truth


@pytest.mark.parametrize("seed", [1, 2])
def test_cylinder_in_clutter(seed: int) -> None:
    mesh, wanted, truth = _cluttered("cylinder", seed, radius=12.5)
    assert isinstance(truth, Cylinder)
    outcome = run_fit(
        mesh,
        np.arange(len(mesh.faces)),
        FitRequest(kind="auto", robust=True, snap=False),
        np.random.default_rng(seed),
    )
    fit = outcome.primitive
    assert isinstance(fit, Cylinder)
    assert angle_deg(fit.axis, truth.axis) < 0.05
    assert abs(fit.radius - truth.radius) < 0.01
    assert line_distance(fit.origin, truth.origin, truth.axis) < 0.02
    # The consensus set is the cylinder: most of its triangles, hardly anything else.
    assert 0.9 * wanted < outcome.stats.face_count < 1.02 * wanted
    assert outcome.stats.excluded_faces == len(mesh.faces) - outcome.stats.face_count
    assert outcome.stats.passed


def test_plane_in_clutter() -> None:
    mesh, wanted, truth = _cluttered("plane", 3)
    assert isinstance(truth, Plane)
    outcome = run_fit(
        mesh,
        np.arange(len(mesh.faces)),
        FitRequest(kind="plane", robust=True, snap=False),
        np.random.default_rng(3),
    )
    fit = outcome.primitive
    assert isinstance(fit, Plane)
    assert angle_deg(fit.normal, truth.normal) < 0.01
    offset = float((np.asarray(fit.origin) - np.asarray(truth.origin)) @ np.asarray(truth.normal))
    assert abs(offset) < 0.005
    assert 0.9 * wanted < outcome.stats.face_count < 1.02 * wanted


def test_plain_least_squares_fails_where_ransac_succeeds() -> None:
    mesh, _, truth = _cluttered("cylinder", 4, radius=12.5)
    assert isinstance(truth, Cylinder)
    faces = np.arange(len(mesh.faces))
    plain = run_fit(mesh, faces, FitRequest(kind="cylinder", snap=False), np.random.default_rng(4))
    assert isinstance(plain.primitive, Cylinder)
    assert abs(plain.primitive.radius - truth.radius) > 0.1 or not plain.stats.passed


def test_fit_robust_returns_consensus_statistics() -> None:
    mesh, _, truth = _cluttered("cylinder", 5, radius=12.5)
    assert isinstance(truth, Cylinder)
    points, normals = mesh.vertices, mesh.jet.normals
    result = fit_robust("cylinder", points, normals, 3 * SIGMA, np.random.default_rng(5))
    assert isinstance(result.primitive, Cylinder)
    assert abs(result.primitive.radius - truth.radius) < 0.01
    assert result.sigma == pytest.approx(SIGMA, rel=0.2)


def test_ransac_is_reproducible_with_the_same_seed() -> None:
    mesh, _, _ = _cluttered("cylinder", 6, radius=12.5)
    faces = np.arange(len(mesh.faces))
    request = FitRequest(kind="cylinder", robust=True, snap=False)
    first = run_fit(mesh, faces, request, np.random.default_rng(42))
    second = run_fit(mesh, faces, request, np.random.default_rng(42))
    assert first.primitive == second.primitive
    assert first.stats == second.stats
