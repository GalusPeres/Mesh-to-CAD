"""Reference planes and axes built from fits of the scanned test block and origin geometry."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from m2c_kernel.codes.reference import ErrorCode
from m2c_kernel.document.ops import AddFeature, NewFeature, UpdateFeature
from m2c_kernel.fitting.api import Plane
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.fitting.helpers import SIGMA, angle_deg, line_distance, scan_document
from tests.fitting.test_fit_feature import add_fit, apply
from tests.synthetic import add_scanner_noise
from tests.synthetic.parts import SyntheticPart, block_part

pytestmark = pytest.mark.occt

HOLE = 14  # D16 through hole at (25, 35)
FRONT, BACK = 8, 9  # planes y = 0 and y = 70
LEFT = 5  # plane x = 0


@pytest.fixture
def block(session: Session, job: JobContext) -> SyntheticPart:
    part = block_part(2.0)
    rng = np.random.default_rng(5)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, SIGMA, rng, spike_fraction=0.001)
    session.commit(scan_document(session, noisy, part.faces), "import", job)
    return part


def fit_face(session: Session, job: JobContext, part: SyntheticPart, face: int) -> str:
    kind = type(part.surfaces[face]).__name__.lower()
    return add_fit(session, job, np.nonzero(part.labels == face)[0], kind=kind, snap=False)


def add_reference(session: Session, job: JobContext, **definition: Any) -> str:
    params = RawObject({"definition": definition})
    apply(session, job, AddFeature(feature=NewFeature(type="reference", params=params)))
    return session.document.features[-1].id


def status(session: Session, job: JobContext, feature_id: str):  # type: ignore[no-untyped-def]
    return session.snapshot("current", job).status.features[feature_id]


def construction(session: Session, job: JobContext, feature_id: str):  # type: ignore[no-untyped-def]
    output = session.built(job).result.outputs[feature_id]
    assert output.construction is not None
    return output.construction


def test_plane_through_the_fitted_hole_axis_at_30_degrees(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    hole = fit_face(session, job, block, HOLE)
    plane_id = add_reference(session, job, type="planeThroughAxis", axis=hole, angleDeg=30.0)
    assert status(session, job, plane_id).state == "ok"
    plane = construction(session, job, plane_id).primitive
    assert isinstance(plane, Plane)
    # About Z, 0 degrees contains X; 30 degrees contains (cos 30, sin 30, 0).
    in_plane = np.array([np.cos(np.radians(30)), np.sin(np.radians(30)), 0.0])
    assert abs(float(np.dot(plane.normal, in_plane))) < 2e-4
    assert abs(float(np.dot(plane.normal, [0.0, 0.0, 1.0]))) < 2e-4
    # The plane contains the hole axis through (25, 35).
    for z in (0.0, 20.0):
        distance = float(np.dot(np.subtract([25.0, 35.0, z], plane.origin), plane.normal))
        assert abs(distance) < 0.01
    stats = status(session, job, plane_id).stats
    assert stats["xDirZ"] == pytest.approx(1.0, abs=1e-3)


def test_mid_plane_of_two_parallel_faces(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    front, back = fit_face(session, job, block, FRONT), fit_face(session, job, block, BACK)
    mid_id = add_reference(session, job, type="midPlane", a=front, b=back)
    plane = construction(session, job, mid_id).primitive
    a = construction(session, job, front).primitive
    b = construction(session, job, back).primitive
    assert isinstance(plane, Plane) and isinstance(a, Plane) and isinstance(b, Plane)
    # Halfway between the two fitted planes, with their mean direction ...
    distance_a = float(np.dot(np.subtract(a.origin, plane.origin), plane.normal))
    distance_b = float(np.dot(np.subtract(b.origin, plane.origin), plane.normal))
    assert distance_a == pytest.approx(-distance_b, abs=1e-6)
    assert angle_deg(plane.normal, np.subtract(b.normal, a.normal)) < 1e-6
    # ... which is the design mid-plane y = 35 within the fit accuracy.
    assert angle_deg(plane.normal, [0.0, 1.0, 0.0]) < 0.05
    assert abs(float(np.dot(plane.origin, [0.0, 1.0, 0.0])) - 35.0) < 0.01


def test_axis_from_two_planes(session: Session, job: JobContext, block: SyntheticPart) -> None:
    left, front = fit_face(session, job, block, LEFT), fit_face(session, job, block, FRONT)
    axis_id = add_reference(session, job, type="axisFromPlanes", a=left, b=front)
    axis = construction(session, job, axis_id).axis
    a = construction(session, job, left).primitive
    b = construction(session, job, front).primitive
    assert axis is not None and isinstance(a, Plane) and isinstance(b, Plane)
    # Exactly the intersection of the fitted planes ...
    assert angle_deg(axis.direction, np.cross(a.normal, b.normal)) < 1e-6
    for plane in (a, b):
        assert abs(float(np.dot(np.subtract(axis.point, plane.origin), plane.normal))) < 1e-9
    # ... which is the design edge x = y = 0 within the fit accuracy.
    assert angle_deg(axis.direction, [0.0, 0.0, 1.0]) < 0.05
    assert line_distance([0.0, 0.0, 10.0], axis.point, axis.direction) < 0.02
    items = session.snapshot("current", job).scene.items
    assert [item.style for item in items if item.owner == axis_id] == ["constructionEdges"]


def test_parallel_planes_have_no_axis(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    front, back = fit_face(session, job, block, FRONT), fit_face(session, job, block, BACK)
    axis_id = add_reference(session, job, type="axisFromPlanes", a=front, b=back)
    result = status(session, job, axis_id)
    assert result.state == "error"
    assert result.error.code == ErrorCode.PARALLEL_PLANES


def test_mid_plane_needs_parallel_planes(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    left, front = fit_face(session, job, block, LEFT), fit_face(session, job, block, FRONT)
    mid_id = add_reference(session, job, type="midPlane", a=left, b=front)
    assert status(session, job, mid_id).error.code == ErrorCode.NOT_PARALLEL


def test_inputs_of_the_wrong_kind_are_reported(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    hole = fit_face(session, job, block, HOLE)
    front = fit_face(session, job, block, FRONT)
    offset_id = add_reference(session, job, type="offsetPlane", plane=hole, distance=5.0)
    assert status(session, job, offset_id).error.code == ErrorCode.NOT_A_PLANE
    axis_id = add_reference(session, job, type="planeThroughAxis", axis=front, angleDeg=0.0)
    assert status(session, job, axis_id).error.code == ErrorCode.NOT_AN_AXIS


def test_offset_plane_from_an_origin_plane_follows_edits(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    plane_id = add_reference(session, job, type="offsetPlane", plane="XY", distance=5.0)
    plane = construction(session, job, plane_id).primitive
    assert isinstance(plane, Plane)
    assert plane.origin[2] == pytest.approx(5.0) and plane.normal == (0.0, 0.0, 1.0)
    params = RawObject({"definition": {"type": "offsetPlane", "plane": "XZ", "distance": -2.5}})
    apply(session, job, UpdateFeature(id=plane_id, params=params))
    plane = construction(session, job, plane_id).primitive
    assert isinstance(plane, Plane)
    assert plane.normal == (0.0, 1.0, 0.0)
    assert plane.origin[1] == pytest.approx(-2.5)


def test_plane_through_an_origin_axis(session: Session, job: JobContext) -> None:
    plane_id = add_reference(session, job, type="planeThroughAxis", axis="Z", angleDeg=90.0)
    plane = construction(session, job, plane_id).primitive
    assert isinstance(plane, Plane)
    np.testing.assert_allclose(np.abs(plane.normal), [1.0, 0.0, 0.0], atol=1e-12)
