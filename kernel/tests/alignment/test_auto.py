"""Automatic alignment: largest planes, then 3-2-1; PCA only without planes."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
import trimesh

from m2c_kernel.alignment.api import evaluate
from m2c_kernel.codes.alignment import IssueCode
from m2c_kernel.document.model import Alignment, AlignmentAdjust
from m2c_kernel.geometry import matrix_array
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.alignment.conftest import pose_scan
from tests.synthetic.parts import SyntheticPart

pytestmark = pytest.mark.occt

AXIS_TOLERANCE_DEG = 0.05
ORIGIN_TOLERANCE_MM = 0.05


def _rotation_error_deg(rotation: np.ndarray) -> float:
    cosine = np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def test_block_in_five_poses_lands_in_the_design_pose(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    for seed in range(5):
        posed = pose_scan(session, block, seed)
        result = evaluate(posed.document, Alignment(method="auto"), job)
        transform = matrix_array(result.matrix)
        # Part axes relative to the design axes: identity means the design pose.
        design_to_part = transform[:3, :3] @ posed.rotation
        assert _rotation_error_deg(design_to_part) < AXIS_TOLERANCE_DEG, seed
        design_origin = transform[:3, :3] @ posed.offset + transform[:3, 3]
        assert np.abs(design_origin).max() < ORIGIN_TOLERANCE_MM, (seed, design_origin)
        assert result.issues == ()
        assert result.largest_plane is not None
        assert result.largest_plane.plane == "XY"
        assert result.largest_plane.tilt_deg < 0.01
        assert result.plane_count >= 4


def test_adjustments_turn_the_part_about_the_new_origin(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = pose_scan(session, block, 11)
    plain = matrix_array(evaluate(posed.document, Alignment(method="auto"), job).matrix)
    flipped = evaluate(
        posed.document, Alignment(method="auto", adjust=AlignmentAdjust(flip_z=True)), job
    )
    turned = matrix_array(flipped.matrix)
    np.testing.assert_allclose(
        turned[:3, :3] @ plain[:3, :3].T, np.diag([1.0, -1.0, -1.0]), atol=1e-9
    )
    corners = _part_points(turned, posed.document, session)
    assert corners.min(axis=0) == pytest.approx([0.0, 0.0, 0.0], abs=0.35)
    assert flipped.largest_plane is not None and flipped.largest_plane.tilt_deg < 0.01

    quarter = evaluate(
        posed.document, Alignment(method="auto", adjust=AlignmentAdjust(rotate_z90=1)), job
    )
    extent = np.ptp(_part_points(matrix_array(quarter.matrix), posed.document, session), axis=0)
    assert extent[0] == pytest.approx(70.0, abs=0.6)
    assert extent[1] == pytest.approx(100.0, abs=0.6)


def _part_points(transform: np.ndarray, document, session: Session) -> np.ndarray:  # type: ignore[no-untyped-def]
    scan = document.scan
    vertices = session.blobs.get(scan.vertices).astype(np.float64) + np.asarray(scan.origin)
    result: np.ndarray = vertices @ transform[:3, :3].T + transform[:3, 3]
    return result


def _egg(seed: int) -> SyntheticPart:
    """A closed surface without planes, asymmetric along all principal axes."""
    sphere = trimesh.creation.icosphere(subdivisions=5, radius=1.0)
    u, v, w = np.asarray(sphere.vertices).T
    vertices = np.column_stack([40 * u + 6 * u**2, 25 * v + 4 * v**2, 12 * w])
    faces = np.asarray(sphere.faces, dtype=np.int64)
    return SyntheticPart(
        shape=None,
        vertices=vertices,
        faces=faces,
        labels=np.zeros(len(faces), dtype=np.int64),
        surfaces=(None,),
    )


def test_pca_fallback_is_deterministic(session: Session, job: JobContext) -> None:
    egg = _egg(0)
    poses = []
    for seed in range(4):
        posed = pose_scan(session, egg, 100 + seed, sigma=0.02)
        result = evaluate(posed.document, Alignment(method="auto"), job)
        assert result.issues == (IssueCode.PCA_FALLBACK,)
        assert result.largest_plane is None
        poses.append(matrix_array(result.matrix)[:3, :3] @ posed.rotation)
    for pose in poses[1:]:
        assert _rotation_error_deg(pose @ poses[0].T) < 0.5
    # The long axis of the egg becomes X, the shortest Z.
    np.testing.assert_allclose(np.abs(poses[0]), np.eye(3), atol=0.02)


def test_single_plane_uses_the_principal_direction(session: Session, job: JobContext) -> None:
    egg = _egg(0)
    flat = replace(
        egg, vertices=np.column_stack([egg.vertices[:, :2], np.maximum(egg.vertices[:, 2], -4.0)])
    )
    posed = pose_scan(session, flat, 7, sigma=0.02)
    result = evaluate(posed.document, Alignment(method="auto"), job)
    assert result.issues == (IssueCode.SINGLE_PLANE,)
    design_to_part = matrix_array(result.matrix)[:3, :3] @ posed.rotation
    np.testing.assert_allclose(design_to_part[2], [0.0, 0.0, 1.0], atol=1e-3)
    np.testing.assert_allclose(np.abs(design_to_part[0]), [1.0, 0.0, 0.0], atol=0.02)
