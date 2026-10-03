"""Signed distances against brute force, the exact solid and the known noise."""

from __future__ import annotations

import time

import numpy as np
import pytest
import trimesh
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT

from m2c_kernel.cad.occ_compat import (
    BRepBuilderAPI_MakeVertex,
    BRepExtrema_DistShapeShape,
    gp_Pnt,
)
from m2c_kernel.document.results import Body
from m2c_kernel.inspection.api import (
    BodyInput,
    ReferenceSurface,
    deviation_map,
    deviation_summary,
    reference_for,
    signed_distances,
)
from m2c_kernel.inspection.distance import closest_on_triangles
from m2c_kernel.session.jobs import JobContext
from tests.inspection.scene import NoisyScan, _block_shape, noisy_block
from tests.timing import budget

pytestmark = pytest.mark.occt

TOLERANCE = 0.1


@pytest.fixture(scope="module")
def scan() -> NoisyScan:
    return noisy_block()


@pytest.fixture(scope="module")
def block() -> BodyInput:
    return BodyInput("f1", "test-block", Body(_block_shape()))


@pytest.fixture(scope="module")
def reference(block: BodyInput) -> ReferenceSurface:
    return reference_for([block], TOLERANCE)


def test_reference_is_a_watertight_tessellation_within_the_deflection(
    reference: ReferenceSurface,
) -> None:
    mesh = trimesh.Trimesh(
        reference.triangles.reshape(-1, 3), np.arange(3 * len(reference.faces)).reshape(-1, 3)
    )
    mesh.merge_vertices()
    assert mesh.is_watertight
    assert reference.deflection == pytest.approx(TOLERANCE / 20)
    assert mesh.volume == pytest.approx(145_747.43, rel=1e-4)
    assert reference.max_edge <= 5.0 + 1e-9
    assert set(np.unique(reference.face_id)) == set(range(16))


def test_point_triangle_routine_matches_trimesh() -> None:
    rng = np.random.default_rng(1)
    corners = rng.normal(size=(20_000, 3, 3))
    points = rng.normal(size=(20_000, 3)) * 2
    closest, _ = closest_on_triangles(points, corners[:, 0], corners[:, 1], corners[:, 2])
    expected = trimesh.triangles.closest_point(corners, points)
    assert np.abs(closest - expected).max() < 1e-9


def test_distances_equal_brute_force_on_20k_points(
    scan: NoisyScan, reference: ReferenceSurface
) -> None:
    rng = np.random.default_rng(2)
    points = scan.vertices[rng.choice(len(scan.vertices), 20_000, replace=False)]
    result = signed_distances(points, reference, max_distance=2.0)
    mesh = trimesh.Trimesh(
        reference.triangles.reshape(-1, 3),
        np.arange(3 * len(reference.faces)).reshape(-1, 3),
        process=False,
    )
    _, exact, _ = trimesh.proximity.closest_point(mesh, points)
    assert np.all(np.isfinite(result.distances))
    assert np.abs(np.abs(result.distances.astype(np.float64)) - exact).max() < 1e-3


def test_signs_agree_with_the_solid_classifier(
    scan: NoisyScan, reference: ReferenceSurface
) -> None:
    rng = np.random.default_rng(3)
    points = scan.vertices[rng.choice(len(scan.vertices), 20_000, replace=False)]
    # Spikes far from the surface as well, on both sides.
    points = np.vstack([points, points[:500] + rng.normal(0, 1.0, (500, 3))])
    distances = signed_distances(points, reference, max_distance=5.0).distances
    far = np.flatnonzero(np.isfinite(distances) & (np.abs(distances) > reference.deflection))
    assert len(far) > 15_000
    classifier = BRepClass3d_SolidClassifier(_block_shape())
    disagreements = 0
    for index in far:
        classifier.Perform(gp_Pnt(*points[index]), 1e-7)
        state = classifier.State()
        assert state in (TopAbs_IN, TopAbs_OUT)
        disagreements += (state == TopAbs_OUT) != (distances[index] > 0)
    assert disagreements == 0


def test_distances_match_the_exact_solid(scan: NoisyScan, reference: ReferenceSurface) -> None:
    rng = np.random.default_rng(8)
    points = scan.vertices[rng.choice(len(scan.vertices), 300, replace=False)]
    distances = signed_distances(points, reference, max_distance=2.0).distances
    solid = _block_shape()
    for point, distance in zip(points, distances, strict=True):
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        exact = BRepExtrema_DistShapeShape(vertex, solid)
        assert exact.IsDone()
        # Only the chord error of the reference tessellation separates the two.
        assert abs(abs(float(distance)) - exact.Value()) <= reference.deflection + 1e-4


def test_distances_reproduce_the_known_noise(scan: NoisyScan, block: BodyInput) -> None:
    job = JobContext.detached()
    synthetic = np.zeros(len(scan.faces), dtype=bool)
    result = deviation_map(scan.vertices, scan.faces, synthetic, [block], TOLERANCE, 2.0, job)
    error = np.abs(result.values.astype(np.float64) - scan.offset)
    # The applied offset is the true distance except within |offset| of a B-Rep edge,
    # where the nearest surface can be the neighbouring face.
    assert np.mean(error < 0.012) > 0.999
    assert result.stats.count == len(scan.vertices)
    assert result.stats.std == pytest.approx(np.std(scan.offset), abs=0.002)
    assert result.stats.within is not None and result.stats.within > 0.99
    assert result.stats.passed
    assert np.isnan(result.face_values).sum() == 0
    assert sum(face.count for face in result.faces) == len(scan.vertices)
    assert {face.face for face in result.faces} == set(range(16))


def test_points_beyond_the_search_distance_and_synthetic_triangles_have_no_value(
    scan: NoisyScan, block: BodyInput
) -> None:
    vertices = scan.vertices.copy()
    vertices[:100] += np.array([0.0, 0.0, 30.0])  # debris far above the part
    synthetic = np.zeros(len(scan.faces), dtype=bool)
    synthetic[-50:] = True
    only_synthetic = np.setdiff1d(scan.faces[-50:].ravel(), scan.faces[:-50].ravel())
    job = JobContext.detached()
    result = deviation_map(vertices, scan.faces, synthetic, [block], TOLERANCE, 2.0, job)
    assert np.isnan(result.values[:100]).all()
    assert np.isnan(result.values[only_synthetic]).all()
    expected = len(scan.vertices) - len(np.union1d(np.arange(100), only_synthetic))
    assert result.stats.count == expected


def test_a_bump_shows_as_positive_deviation_on_its_face(block: BodyInput) -> None:
    scan = noisy_block()
    vertices = scan.vertices.copy()
    top = np.abs(vertices[:, 2] - 20.0) < 0.2
    bump = top & (np.linalg.norm(vertices[:, :2] - [15.0, 55.0], axis=1) < 6.0)
    vertices[bump, 2] += 0.3
    job = JobContext.detached()
    synthetic = np.zeros(len(scan.faces), dtype=bool)
    result = deviation_map(vertices, scan.faces, synthetic, [block], TOLERANCE, 2.0, job)
    assert np.nanmedian(result.values[bump]) == pytest.approx(0.3, abs=0.02)
    worst = min(result.faces, key=lambda face: face.within)
    assert worst.mean > 0.0 and worst.within < 0.99


def test_preview_summary_is_fast_and_consistent(scan: NoisyScan) -> None:
    body = BodyInput("f9", "preview-block", Body(_block_shape()))
    rng = np.random.default_rng(4)
    start = time.perf_counter()
    stats, points = deviation_summary(scan.vertices, [body], TOLERANCE, 2.0, rng)
    elapsed = time.perf_counter() - start
    # Interactive budget: one second.
    assert elapsed < budget(1.0)
    assert points == 50_000
    assert stats.count == points
    assert stats.std == pytest.approx(np.std(scan.offset), abs=0.003)
