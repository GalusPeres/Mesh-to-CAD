"""The fit feature in the rebuild, and the `fit.preview` and `fit.featureFaces` commands."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from m2c_kernel.codes.fit import ErrorCode, IssueCode
from m2c_kernel.commands.doc import ApplyParams, doc_apply
from m2c_kernel.commands.fit import (
    FeatureFacesParams,
    PreviewParams,
    fit_feature_faces,
    fit_preview,
)
from m2c_kernel.document.model import DocumentSettings
from m2c_kernel.document.ops import AddFeature, NewFeature, SetSettings, UpdateFeature
from m2c_kernel.features.types.fit import FitFixed, FitRelation
from m2c_kernel.fitting.api import Cylinder, FaceState, Plane
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import RawObject, to_json
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.fitting.helpers import combine, noisy_patch, scan_document


def fit_input(faces: np.ndarray, **params: Any) -> RawObject:
    """Fit parameters as the renderer sends them: triangles as a uint32 buffer."""
    array = np.ascontiguousarray(faces, dtype=np.uint32)
    reference = {"$buf": 0, "dtype": "uint32", "shape": [len(array)]}
    return RawObject({"faces": reference, **params}, (memoryview(array).cast("B"),))


def apply(session: Session, job: JobContext, *ops: Any) -> None:
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=list(ops), label="t"))


def add_fit(session: Session, job: JobContext, faces: np.ndarray, **params: Any) -> str:
    feature = NewFeature(type="fit", params=fit_input(faces, **params))
    apply(session, job, AddFeature(feature=feature))
    return session.document.features[-1].id


class Scene:
    """A hole (R8, 120 degrees, axis parallel to Z) next to a plane at z = 12."""

    def __init__(self, session: Session, job: JobContext, synthetic_share: float = 0.0) -> None:
        hole = noisy_patch("cylinder", np.radians(120), 20.0, 1, pose=False, radius=8.0)
        plane = noisy_patch("plane", 30.0, 30.0, 2, pose=False)
        shifted = (hole.vertices + np.array([20.0, 10.0, 0.0]), hole.faces)
        raised = (plane.vertices + np.array([60.0, 0.0, 12.0]), plane.faces)
        vertices, faces = combine(shifted, raised)
        self.hole = np.arange(len(hole.faces))
        self.plane = np.arange(len(hole.faces), len(faces))
        synthetic = np.zeros(len(faces), dtype=bool)
        if synthetic_share:
            synthetic[self.hole[: int(synthetic_share * len(self.hole))]] = True
        self.synthetic = synthetic
        document = scan_document(session, vertices, faces, synthetic=synthetic)
        session.commit(document, "import", job)
        assert session.document.scan is not None
        self.scan_key = session.document.scan.key


def _status(session: Session, job: JobContext, feature_id: str):  # type: ignore[no-untyped-def]
    return session.snapshot("current", job).status.features[feature_id]


def test_a_fit_feature_stores_its_triangles_and_snaps(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    feature_id = add_fit(session, job, scene.hole[::-1], kind="cylinder")
    status = _status(session, job, feature_id)
    assert status.state == "ok"
    assert status.stats["radius"] == 8.0
    assert status.stats["directionZ"] == 1.0
    assert status.stats["snap.radius.value"] == 8.0
    assert abs(status.stats["snap.radius.measured"] - 8.0) < 0.02
    assert status.stats["snap.direction.target"] == 2.0
    assert status.stats["faceCount"] == len(scene.hole)
    assert status.stats["concave"] == 0.0
    stored = fit_feature_faces(job, FeatureFacesParams(feature_id=feature_id))
    np.testing.assert_array_equal(stored.faces, np.sort(scene.hole))
    assert stored.scan_key == scene.scan_key
    items = session.snapshot("current", job).scene.items
    assert {item.style for item in items if item.owner == feature_id} == {
        "construction",
        "constructionEdges",
    }


def test_tolerance_change_reevaluates_and_fixed_values_stay(
    session: Session, job: JobContext
) -> None:
    scene = Scene(session, job)
    fixed = FitFixed(radius=8.05)
    feature_id = add_fit(session, job, scene.hole, kind="cylinder", fixed=to_json(fixed, FitFixed))
    before = _status(session, job, feature_id)
    assert before.stats["radius"] == 8.05
    assert before.stats["tolerance"] == pytest.approx(0.1)
    settings = replace(session.document.settings, tolerance=0.02)
    apply(session, job, SetSettings(settings=settings))
    after = _status(session, job, feature_id)
    assert after.stats["radius"] == 8.05
    assert after.stats["tolerance"] == pytest.approx(0.02)
    assert after.stats["withinTolerance"] < before.stats["withinTolerance"]
    assert after.state == "warning"
    assert after.issues[0].code == IssueCode.POOR_FIT


def test_synthetic_triangles_are_excluded(session: Session, job: JobContext) -> None:
    scene = Scene(session, job, synthetic_share=0.3)
    feature_id = add_fit(session, job, scene.hole, kind="cylinder")
    status = _status(session, job, feature_id)
    synthetic = int(scene.synthetic.sum())
    assert status.stats["faceCount"] == len(scene.hole) - synthetic
    assert status.stats["excludedFaces"] == synthetic
    preview = fit_preview(
        job, PreviewParams(faces=scene.hole.astype(np.uint32), scan_key=scene.scan_key)
    )
    assert (preview.face_states[scene.synthetic[scene.hole]] == FaceState.NONE).all()
    np.testing.assert_array_equal(preview.used, ~scene.synthetic[scene.hole])
    assert (preview.face_states[~scene.synthetic[scene.hole]] != FaceState.NONE).all()


def test_preview_matches_the_committed_feature(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    preview = fit_preview(
        job, PreviewParams(faces=scene.plane.astype(np.uint32), scan_key=scene.scan_key)
    )
    assert isinstance(preview.primitive, Plane)
    assert preview.primitive.normal == (0.0, 0.0, 1.0)
    assert preview.primitive.origin[2] == pytest.approx(12.0, abs=1e-9)
    assert [snap.id for snap in preview.snaps] == ["direction", "offset"]
    assert len(preview.face_states) == len(scene.plane)
    assert preview.stats.passed
    assert {item.style for item in preview.items} == {"construction", "constructionEdges"}
    assert preview.alternatives[0].kind == "plane"
    feature_id = add_fit(session, job, scene.plane, kind="plane")
    assert _status(session, job, feature_id).stats["offset"] == pytest.approx(12.0, abs=1e-9)


def test_relation_to_another_fit(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    hole = add_fit(session, job, scene.hole, kind="cylinder", snap=False)
    relation = {"type": "perpendicular", "to": hole}
    preview = fit_preview(
        job,
        PreviewParams(
            faces=scene.plane.astype(np.uint32),
            scan_key=scene.scan_key,
            kind="plane",
            relation=FitRelation(type="perpendicular", to=hole),
            snap=False,
        ),
    )
    assert isinstance(preview.primitive, Plane)
    axis = session.snapshot("current", job).status.features[hole].stats
    hole_axis = np.array([axis["directionX"], axis["directionY"], axis["directionZ"]])
    # A plane perpendicular to an axis has the axis as its normal.
    assert abs(abs(float(np.dot(preview.primitive.normal, hole_axis))) - 1.0) < 1e-12
    plane = add_fit(session, job, scene.plane, kind="plane", relation=relation)
    assert _status(session, job, plane).state in ("ok", "warning")
    ids = [feature.id for feature in session.document.features]
    assert ids == [hole, plane]


def test_preview_errors(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    with pytest.raises(KernelError) as stale:
        fit_preview(job, PreviewParams(faces=scene.plane.astype(np.uint32), scan_key="scan:old"))
    assert stale.value.code == ErrorCode.STALE_SELECTION
    with pytest.raises(KernelError) as few:
        fit_preview(
            job, PreviewParams(faces=scene.plane[:50].astype(np.uint32), scan_key=scene.scan_key)
        )
    assert few.value.code == ErrorCode.TOO_FEW_FACES
    assert few.value.params == {"count": 50, "min": 200}
    with pytest.raises(KernelError) as wrong:
        fit_preview(
            job,
            PreviewParams(
                faces=scene.plane.astype(np.uint32),
                scan_key=scene.scan_key,
                kind="plane",
                fixed=FitFixed(radius=3.0),
            ),
        )
    assert wrong.value.code == ErrorCode.FIXED_NOT_APPLICABLE


def test_editing_a_fit_replaces_its_triangles(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    feature_id = add_fit(session, job, scene.hole, kind="cylinder")
    half = scene.hole[: len(scene.hole) // 2]
    apply(session, job, UpdateFeature(id=feature_id, params=fit_input(half, kind="cylinder")))
    status = _status(session, job, feature_id)
    assert status.stats["faceCount"] == len(half)
    stored = fit_feature_faces(job, FeatureFacesParams(feature_id=feature_id))
    np.testing.assert_array_equal(stored.faces, half)


def test_fit_preview_of_100k_faces_takes_less_than_300_ms(
    session: Session, job: JobContext
) -> None:
    patch = noisy_patch(
        "cylinder", np.radians(150), 60.0, 3, pose=False, radius=20.0, resolution=225
    )
    assert len(patch.faces) > 100_000
    document = scan_document(session, patch.vertices, patch.faces, settings=DocumentSettings())
    session.commit(document, "import", job)
    assert session.document.scan is not None
    built = session.built(job)
    assert built.result.mesh is not None
    _ = built.result.mesh.jet, built.result.mesh.face_centroids  # computed once per scan
    params = PreviewParams(
        faces=np.arange(len(patch.faces), dtype=np.uint32), scan_key=session.document.scan.key
    )
    timings = []
    for _ in range(3):
        start = time.perf_counter()
        result = fit_preview(job, params)
        timings.append(time.perf_counter() - start)
    assert isinstance(result.primitive, Cylinder)
    assert result.primitive.radius == 20.0
    assert min(timings) < 0.3, timings


def test_fixed_values_outside_their_range_are_rejected(session: Session, job: JobContext) -> None:
    scene = Scene(session, job)
    faces = scene.hole.astype(np.uint32)
    for fixed in (FitFixed(radius=0.0), FitFixed(radius=-2.0)):
        with pytest.raises(KernelError) as invalid:
            fit_preview(
                job,
                PreviewParams(faces=faces, scan_key=scene.scan_key, kind="cylinder", fixed=fixed),
            )
        assert invalid.value.code == ErrorCode.INVALID_VALUE
