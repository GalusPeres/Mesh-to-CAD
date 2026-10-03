"""Measurements between fits of the noisy test block, exact faces and origin items."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from m2c_kernel.cad.occ_compat import (
    BRepPrimAPI_MakeBox,
    TopAbs_FACE,
    TopoDS,
    indexed_map,
)
from m2c_kernel.fitting.api import Primitive, PrimitiveKind, fit_primitive
from m2c_kernel.inspection.api import (
    Geometry,
    Item,
    fit_covariance,
    geometry_of_face,
    geometry_of_origin,
    geometry_of_primitive,
    measure_items,
)
from m2c_kernel.inspection.measure import measure
from tests.inspection.scene import NoisyScan, _block_shape, noisy_block

pytestmark = pytest.mark.occt

TOP, BOTTOM, BOSS, HOLE, SPHERE = 4, 15, 0, 14, 13


@pytest.fixture(scope="module")
def scan() -> NoisyScan:
    return noisy_block()


def _points(scan: NoisyScan, label: int) -> np.ndarray:
    return scan.vertices[np.unique(scan.faces[scan.labels == label].ravel())]


def _fit(scan: NoisyScan, label: int, kind: PrimitiveKind) -> tuple[Primitive, np.ndarray]:
    points = _points(scan, label)
    mesh = trimesh.Trimesh(scan.vertices, scan.faces, process=False)
    normals = np.asarray(mesh.vertex_normals)[np.unique(scan.faces[scan.labels == label])]
    result = fit_primitive(kind, points, normals, np.random.default_rng(label))
    return result.primitive, points


def _item(scan: NoisyScan, label: int, kind: PrimitiveKind) -> Item:
    primitive, points = _fit(scan, label, kind)
    covariance = fit_covariance(primitive, points, np.random.default_rng(100 + label))
    return Item(geometry_of_primitive(primitive), covariance)


def test_distance_between_parallel_fitted_planes(scan: NoisyScan) -> None:
    result = measure_items(
        _item(scan, TOP, "plane"), _item(scan, BOTTOM, "plane"), np.random.default_rng(1)
    )
    assert result.parallel and result.distance_kind == "parallel"
    assert result.distance == pytest.approx(20.0, abs=0.003)
    assert result.angle is not None and result.angle < 0.02
    assert result.distance_sigma is not None and 0.0 < result.distance_sigma < 0.002
    assert result.angle_sigma is not None and result.angle_sigma < 0.02


def test_angle_and_distance_between_fitted_axes(scan: NoisyScan) -> None:
    boss, hole = _item(scan, BOSS, "cylinder"), _item(scan, HOLE, "cylinder")
    result = measure_items(boss, hole, np.random.default_rng(2))
    assert result.parallel
    assert result.angle is not None and result.angle < 0.05
    assert result.distance == pytest.approx(45.0, abs=0.01)
    assert result.diameter_a == pytest.approx(30.0, abs=0.02)
    assert result.diameter_b == pytest.approx(16.0, abs=0.02)
    assert result.diameter_a_sigma is not None and 0.0 < result.diameter_a_sigma < 0.01
    assert result.distance_sigma is not None and 0.0 < result.distance_sigma < 0.02


def test_uncertainty_matches_the_scatter_of_repeated_scans() -> None:
    """The propagated sigma describes how much the value varies between noisy scans."""
    distances, sigmas = [], []
    for seed in range(6):
        scan = noisy_block(seed=100 + seed)
        result = measure_items(
            _item(scan, TOP, "plane"), _item(scan, BOTTOM, "plane"), np.random.default_rng(seed)
        )
        assert result.distance is not None and result.distance_sigma is not None
        distances.append(result.distance)
        sigmas.append(result.distance_sigma)
    scatter = float(np.std(distances, ddof=1))
    assert scatter < 4.0 * float(np.mean(sigmas))
    assert float(np.mean(sigmas)) < 5.0 * max(scatter, 1e-5)


def test_plane_and_axis_are_perpendicular(scan: NoisyScan) -> None:
    result = measure_items(
        _item(scan, TOP, "plane"), _item(scan, BOSS, "cylinder"), np.random.default_rng(3)
    )
    assert not result.parallel and result.distance is None
    assert result.angle == pytest.approx(90.0, abs=0.05)


def test_sphere_centre_to_plane(scan: NoisyScan) -> None:
    result = measure_items(
        _item(scan, SPHERE, "sphere"), Item(geometry_of_origin("XY")), np.random.default_rng(4)
    )
    assert result.distance_kind == "point"
    assert result.distance == pytest.approx(26.0, abs=0.02)
    assert result.diameter_a == pytest.approx(18.0, abs=0.02)


def _face(shape: object, index: int) -> Geometry:
    faces = indexed_map(shape, TopAbs_FACE)
    return geometry_of_face(TopoDS.Face(faces.FindKey(index + 1)))


def _face_index(shape: object, predicate: object) -> int:
    faces = indexed_map(shape, TopAbs_FACE)
    for index in range(faces.Extent()):
        geometry = geometry_of_face(TopoDS.Face(faces.FindKey(index + 1)))
        if predicate(geometry):  # type: ignore[operator]
            return index
    raise LookupError


def test_exact_faces_measure_exactly() -> None:
    shape = _block_shape()
    top = _face_index(shape, lambda g: g.kind == "plane" and abs(g.point[2] - 20.0) < 1e-9)
    hole = _face_index(shape, lambda g: g.kind == "axis" and g.diameter == pytest.approx(16.0))
    rng = np.random.default_rng(0)
    result = measure_items(Item(_face(shape, top)), Item(geometry_of_origin("XY")), rng)
    assert result.distance == pytest.approx(20.0, abs=1e-9)
    assert result.distance_sigma is None
    single = measure_items(Item(_face(shape, hole)), None, rng)
    assert single.diameter_a == pytest.approx(16.0, abs=1e-9)
    assert single.distance is None


def test_faces_without_an_analytic_surface_use_the_minimum_distance() -> None:
    box = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
    faces = indexed_map(box, TopAbs_FACE)
    low = geometry_of_face(TopoDS.Face(faces.FindKey(1)))
    high = geometry_of_face(TopoDS.Face(faces.FindKey(2)))
    as_surface = Geometry("surface", np.zeros(3), shape=low.shape)
    result = measure(as_surface, high)
    assert result.distance_kind == "minimum"
    assert result.distance == pytest.approx(10.0)
    assert result.angle is None


def test_intersecting_planes_have_an_angle_but_no_distance() -> None:
    result = measure(geometry_of_origin("XY"), geometry_of_origin("XZ"))
    assert result.distance is None and result.angle == pytest.approx(90.0)
    skew = measure(
        Geometry("axis", np.array([0.0, 0.0, 5.0]), np.array([1.0, 0.0, 0.0])),
        geometry_of_origin("Y"),
    )
    assert skew.distance_kind == "shortest"
    assert skew.distance == pytest.approx(5.0)
    assert skew.angle == pytest.approx(90.0)
