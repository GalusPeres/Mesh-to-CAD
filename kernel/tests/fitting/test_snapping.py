"""Design-intent snapping: directions, values, units, rejected snaps and the 5 % rule."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.api import (
    Constraints,
    Cylinder,
    FitRequest,
    Plane,
    cluster_directions,
    refine_constrained,
    run_fit,
    snap_fit,
)
from m2c_kernel.geometry import unit
from m2c_kernel.snapping import INCH_MM
from tests.fitting.helpers import noisy_patch

SHIFT = np.array([30.0, 12.0, 5.0])


def _rotation(axis: tuple[float, float, float], degrees: float) -> np.ndarray:
    k = unit(np.asarray(axis, dtype=float))
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    angle = np.radians(degrees)
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross


def _mesh(vertices: np.ndarray, faces: np.ndarray) -> EvalMesh:
    return EvalMesh("mesh:snap", vertices, faces, None)


def _cylinder(radius: float, span_deg: float, length: float, seed: int, tilt=None):  # type: ignore[no-untyped-def]
    patch = noisy_patch(
        "cylinder", np.radians(span_deg), length, seed, pose=False, radius=radius, resolution=120
    )
    vertices = patch.vertices if tilt is None else patch.vertices @ _rotation(*tilt).T
    return _mesh(vertices + SHIFT, patch.faces), np.arange(len(patch.faces))


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_60_degree_arc_of_r4_snaps_to_4(seed: int) -> None:
    mesh, faces = _cylinder(4.0, 60.0, 5.0, seed)
    free = run_fit(mesh, faces, FitRequest(kind="cylinder", snap=False), np.random.default_rng(1))
    snapped = run_fit(mesh, faces, FitRequest(kind="cylinder"), np.random.default_rng(1))
    assert isinstance(snapped.primitive, Cylinder)
    assert snapped.primitive.radius == 4.0
    assert snapped.primitive.axis == (0.0, 0.0, 1.0)
    by_id = {snap.id: snap for snap in snapped.snaps}
    assert by_id["direction"].target == "Z" and by_id["direction"].value == 0.0
    radius = by_id["radius"]
    assert radius.kind == "length" and radius.value == 4.0
    assert abs(radius.measured - 4.0) < 3 * radius.uncertainty
    assert snapped.stats.rms <= 1.05 * free.stats.rms


def test_tilted_control_snaps_neither_axis_nor_radius() -> None:
    mesh, faces = _cylinder(6.37, 359.0, 20.0, 7, tilt=((1.0, 1.0, 0.0), 3.0))
    outcome = run_fit(mesh, faces, FitRequest(kind="auto"), np.random.default_rng(1))
    assert isinstance(outcome.primitive, Cylinder)
    assert outcome.snaps == []
    assert abs(outcome.primitive.radius - 6.37) < 0.005
    assert abs(np.degrees(np.arccos(outcome.primitive.axis[2])) - 3.0) < 0.01


def test_tilt_about_x_keeps_the_axis_perpendicular_to_x_only() -> None:
    mesh, faces = _cylinder(6.37, 359.0, 20.0, 7, tilt=((1.0, 0.0, 0.0), 3.0))
    outcome = run_fit(mesh, faces, FitRequest(kind="auto"), np.random.default_rng(1))
    assert [(snap.id, snap.value, snap.target) for snap in outcome.snaps] == [
        ("direction", 90.0, "X")
    ]
    assert isinstance(outcome.primitive, Cylinder)
    assert outcome.primitive.axis[0] == pytest.approx(0.0, abs=1e-12)


def test_a_candidate_that_raises_the_rms_by_more_than_5_percent_is_rejected() -> None:
    mesh, faces = _cylinder(6.37, 359.0, 20.0, 8)
    points = mesh.vertices
    rng = np.random.default_rng(1)
    start = run_fit(mesh, faces, FitRequest(kind="cylinder", snap=False), rng).primitive
    base = refine_constrained(start, points, Constraints(), rng, solve=False)
    # Pretend the radius were poorly determined, so 6.35 (0.02 away) becomes a candidate.
    loose = replace(base, uncertainty={**base.uncertainty, "radius": 0.02})
    outcome = snap_fit(loose, points, Constraints(), rng, units="metric")
    assert "radius" not in [snap.id for snap in outcome.snaps]
    assert isinstance(outcome.fit.primitive, Cylinder)
    assert abs(outcome.fit.primitive.radius - 6.37) < 0.005


def test_inch_mode_snaps_a_quarter_inch_radius_to_6_35() -> None:
    mesh, faces = _cylinder(0.25 * INCH_MM, 180.0, 10.0, 9)
    outcome = run_fit(
        mesh, faces, FitRequest(kind="cylinder", units="inch"), np.random.default_rng(1)
    )
    assert isinstance(outcome.primitive, Cylinder)
    assert outcome.primitive.radius == pytest.approx(6.35, abs=1e-12)


def test_inch_fractions_snap_only_in_inch_mode() -> None:
    mesh, faces = _cylinder(3 / 16 * INCH_MM, 359.0, 10.0, 10)
    metric = run_fit(mesh, faces, FitRequest(kind="cylinder"), np.random.default_rng(1))
    inch = run_fit(mesh, faces, FitRequest(kind="cylinder", units="inch"), np.random.default_rng(1))
    assert "radius" not in [snap.id for snap in metric.snaps]
    assert isinstance(inch.primitive, Cylinder)
    assert inch.primitive.radius == pytest.approx(4.7625, abs=1e-12)


def test_rejected_snaps_are_not_applied_again() -> None:
    mesh, faces = _cylinder(4.0, 90.0, 8.0, 11)
    no_radius = run_fit(
        mesh,
        faces,
        FitRequest(kind="cylinder", rejected=frozenset({"radius"})),
        np.random.default_rng(1),
    )
    assert [snap.id for snap in no_radius.snaps] == ["direction"]
    assert isinstance(no_radius.primitive, Cylinder) and no_radius.primitive.radius != 4.0
    no_direction = run_fit(
        mesh,
        faces,
        FitRequest(kind="cylinder", rejected=frozenset({"direction"})),
        np.random.default_rng(1),
    )
    assert "direction" not in [snap.id for snap in no_direction.snaps]
    assert isinstance(no_direction.primitive, Cylinder)
    assert no_direction.primitive.axis != (0.0, 0.0, 1.0)


def test_fixed_values_are_kept_and_not_snapped() -> None:
    mesh, faces = _cylinder(4.0, 90.0, 8.0, 12)
    constraints = Constraints(radius=4.05, direction=np.array([0.0, 0.0, 1.0]))
    outcome = run_fit(
        mesh, faces, FitRequest(kind="cylinder", constraints=constraints), np.random.default_rng(1)
    )
    assert isinstance(outcome.primitive, Cylinder)
    assert outcome.primitive.radius == 4.05
    assert outcome.snaps == []
    assert "radius" not in outcome.stats.uncertainty
    assert not outcome.stats.passed or outcome.stats.rms > 0.03


def test_axis_parallel_plane_snaps_its_offset() -> None:
    patch = noisy_patch("plane", 30.0, 30.0, 13, pose=False)
    vertices = patch.vertices @ _rotation((1.0, 0.0, 0.0), 0.004).T + np.array([5.0, 8.0, 20.003])
    outcome = run_fit(
        _mesh(vertices, patch.faces),
        np.arange(len(patch.faces)),
        FitRequest(kind="plane"),
        np.random.default_rng(1),
    )
    assert isinstance(outcome.primitive, Plane)
    assert outcome.primitive.normal == (0.0, 0.0, 1.0)
    assert outcome.primitive.origin[2] == pytest.approx(20.0, abs=1e-9)
    assert [snap.id for snap in outcome.snaps] == ["direction", "offset"]


def test_tilted_plane_gets_no_offset_snap() -> None:
    patch = noisy_patch("plane", 30.0, 30.0, 14, pose=False)
    vertices = patch.vertices @ _rotation((1.0, 1.0, 0.0), 20.0).T + np.array([0.0, 0.0, 20.0])
    outcome = run_fit(
        _mesh(vertices, patch.faces),
        np.arange(len(patch.faces)),
        FitRequest(kind="plane"),
        np.random.default_rng(1),
    )
    assert outcome.snaps == []


def test_direction_clusters_lock_to_axes_and_become_perpendicular() -> None:
    tilt = _rotation((0.0, 0.0, 1.0), 30.0)
    directions = np.array(
        [
            [0.0, 0.0012, 1.0],  # nearly Z
            [0.0, -0.0008, -1.0],  # nearly -Z
            tilt @ [1.0, 0.0, 0.004],  # 30 degrees about Z, slightly tilted up
            tilt @ [0.0, 1.0, -0.003],  # its perpendicular partner
        ]
    )
    snapped, cluster = cluster_directions(directions, [4.0, 1.0, 2.0, 1.0])
    np.testing.assert_allclose(snapped[0], [0, 0, 1], atol=1e-12)
    np.testing.assert_allclose(snapped[1], [0, 0, -1], atol=1e-12)
    assert cluster[0] == cluster[1]
    assert abs(snapped[2] @ [0, 0, 1]) < 1e-12
    assert abs(snapped[3] @ [0, 0, 1]) < 1e-12
    assert abs(snapped[2] @ snapped[3]) < 1e-12
    unlocked, _ = cluster_directions(directions, [4.0, 1.0, 2.0, 1.0], lock_global_axes=False)
    assert abs(unlocked[0] @ [0, 0, 1]) < 1.0
