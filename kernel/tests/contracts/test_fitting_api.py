"""Contracts of the fitting core: parameterisation, signed distances and plain fits."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.fitting.api import (
    Cone,
    Cylinder,
    Plane,
    Sphere,
    Torus,
    fit_best,
    fit_primitive,
    signed_distance,
    surface_normals,
)
from tests.synthetic import add_scanner_noise, primitive_patch, random_pose

SIGMA = 0.03


def _angle_deg(a: tuple[float, float, float], b: np.ndarray) -> float:
    cosine = abs(float(np.dot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(min(cosine, 1.0))))


@pytest.mark.parametrize(
    ("primitive", "point", "expected"),
    [
        (Plane(origin=(0, 0, 0), normal=(0, 0, 1)), (1, 2, 3), 3.0),
        (Sphere(center=(0, 0, 0), radius=2), (3, 0, 0), 1.0),
        (Cylinder(origin=(0, 0, 0), axis=(0, 0, 1), radius=2), (0, 1, 5), -1.0),
        (Torus(center=(0, 0, 0), axis=(0, 0, 1), major_radius=10, minor_radius=2), (13, 0, 0), 1.0),
    ],
)
def test_signed_distance_is_positive_outside(
    primitive: object, point: tuple, expected: float
) -> None:
    assert signed_distance(primitive, np.array([point], float))[0] == pytest.approx(expected)


def test_cone_distance_is_zero_on_the_surface() -> None:
    cone = Cone(apex=(0, 0, 0), axis=(0, 0, 1), half_angle=np.radians(45))
    assert signed_distance(cone, np.array([[1.0, 0.0, 1.0]]))[0] == pytest.approx(0.0, abs=1e-12)


def test_surface_normals_are_distance_gradients() -> None:
    sphere = Sphere(center=(0, 0, 0), radius=5)
    normals = surface_normals(sphere, np.array([[10.0, 0.0, 0.0]]))
    np.testing.assert_allclose(normals[0], [1.0, 0.0, 0.0], atol=1e-6)


@pytest.mark.parametrize("seed", [1, 2])
def test_cylinder_fit_on_a_noisy_90_degree_arc(seed: int) -> None:
    rng = np.random.default_rng(seed)
    patch = primitive_patch("cylinder", np.pi / 2, 40.0, resolution=200, radius=12.5)
    noisy = add_scanner_noise(patch.vertices, patch.normals, SIGMA, rng, spike_fraction=0.001)
    points, normals, rotation, _ = random_pose(noisy, patch.normals, rng)
    fit = fit_primitive("cylinder", points, normals, rng)
    assert isinstance(fit.primitive, Cylinder)
    assert fit.primitive.radius == pytest.approx(12.5, abs=0.01)
    assert _angle_deg(fit.primitive.axis, rotation @ np.array([0.0, 0.0, 1.0])) < 0.01
    assert fit.sigma == pytest.approx(SIGMA, rel=0.1)
    assert fit.concave is False


def test_plane_fit_on_a_noisy_patch() -> None:
    rng = np.random.default_rng(5)
    patch = primitive_patch("plane", 40.0, 40.0, resolution=200)
    noisy = add_scanner_noise(patch.vertices, patch.normals, SIGMA, rng)
    fit = fit_primitive("plane", noisy, patch.normals, rng)
    assert isinstance(fit.primitive, Plane)
    assert _angle_deg(fit.primitive.normal, np.array([0.0, 0.0, 1.0])) < 0.01
    assert fit.primitive.normal[2] > 0
    assert abs(fit.primitive.origin[2]) < 0.005


@pytest.mark.parametrize("kind", ["plane", "sphere", "cylinder"])
def test_automatic_type_choice(kind: str) -> None:
    rng = np.random.default_rng(11)
    spans = {"plane": (40.0, 40.0), "sphere": (np.pi / 2, np.pi / 3), "cylinder": (np.pi, 30.0)}
    patch = primitive_patch(kind, *spans[kind], resolution=150, radius=15.0)
    noisy = add_scanner_noise(patch.vertices, patch.normals, SIGMA, rng)
    winner, alternatives = fit_best(noisy, patch.normals, rng, noise=SIGMA)
    assert winner.kind == kind
    assert alternatives
    assert alternatives[0].sigma <= alternatives[-1].sigma
