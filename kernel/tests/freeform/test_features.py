"""The freeformPatch and loft feature types in a rebuild, and the patch preview command."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import TopAbs_FACE, TopoDS_Shape, indexed_map
from m2c_kernel.commands.freeform import (
    FeatureFacesParams,
    FreeformPreviewParams,
    LoftAxisParams,
    freeform_feature_faces,
    freeform_loft_axis,
    freeform_preview,
)
from m2c_kernel.document.rebuild import rebuild
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.freeform.conftest import scan_document, with_feature
from tests.freeform.shapes import height_field_scan, tube_scan, tube_volume

pytestmark = pytest.mark.occt

SIGMA = 0.02


def test_freeform_patch_feature(session: Session, job: JobContext) -> None:
    field = height_field_scan(sigma=SIGMA)
    document = scan_document(session, field.vertices, field.faces, noise=SIGMA)
    faces = session.blobs.put(np.arange(len(field.faces), dtype=np.uint32))
    document = with_feature(
        document, "f1", "freeformPatch", {"faces": faces, "spans": [16, 12], "margin": 2.0}
    )
    result = rebuild(document, session.environment(), job)
    status = result.statuses["f1"]
    assert status.state == "ok", status.error
    stats = status.stats
    assert stats["freeform.stats.rms"] is not None and stats["freeform.stats.rms"] <= 1.2 * SIGMA
    assert stats["freeform.stats.withinTolerance"] == pytest.approx(1.0)
    assert stats["freeform.stats.spansU"] == 16 and stats["freeform.stats.spansV"] == 12
    construction = result.outputs["f1"].construction
    assert construction is not None and isinstance(construction.surface, TopoDS_Shape)
    assert indexed_map(construction.surface, TopAbs_FACE).Extent() == 1
    styles = [(source.kind, source.style) for source in result.outputs["f1"].display]
    assert styles == [("mesh", "patch"), ("lines", "patch")]


def test_poor_patch_reports_an_issue(session: Session, job: JobContext) -> None:
    field = height_field_scan(sigma=SIGMA)
    document = scan_document(session, field.vertices, field.faces, noise=SIGMA, tolerance=0.02)
    faces = session.blobs.put(np.arange(len(field.faces), dtype=np.uint32))
    document = with_feature(document, "f1", "freeformPatch", {"faces": faces, "spans": [2, 2]})
    status = rebuild(document, session.environment(), job).statuses["f1"]
    assert status.state == "warning"
    assert [issue.code for issue in status.issues] == ["freeform.poorFit"]


def test_too_few_triangles(session: Session, job: JobContext) -> None:
    field = height_field_scan(sigma=SIGMA)
    document = scan_document(session, field.vertices, field.faces, noise=SIGMA)
    faces = session.blobs.put(np.arange(50, dtype=np.uint32))
    document = with_feature(document, "f1", "freeformPatch", {"faces": faces})
    status = rebuild(document, session.environment(), job).statuses["f1"]
    assert status.state == "error" and status.error is not None
    assert status.error.code == "freeform.tooFewFaces"


def test_preview_colours_the_requested_triangles(session: Session, job: JobContext) -> None:
    field = height_field_scan(sigma=SIGMA)
    session.commit(scan_document(session, field.vertices, field.faces, noise=SIGMA), "scan", job)
    requested = np.arange(0, len(field.faces), 2, dtype=np.uint32)
    preview = freeform_preview(job, FreeformPreviewParams(faces=requested))
    assert preview.passed and preview.rms <= 1.2 * SIGMA
    assert preview.face_count == len(requested)
    assert len(preview.face_states) == len(requested)
    assert np.all(preview.face_states == 1)
    assert {item.style for item in preview.items} == {"patch"}
    assert preview.normal_spread_deg < 90.0


def test_loft_feature_with_tags_and_union(session: Session, job: JobContext) -> None:
    vertices, faces = tube_scan(sigma=SIGMA)
    document = scan_document(session, vertices, faces, noise=SIGMA)
    document = with_feature(
        document, "f1", "loft", {"path": "Z", "start": 2.0, "end": 30.0, "sectionCount": 8}
    )
    result = rebuild(document, session.environment(), job)
    assert result.statuses["f1"].state == "ok", result.statuses["f1"].error
    body = result.bodies["f1"]
    assert sorted(body.face_tags) == ["f1:cap:end", "f1:cap:start", "f1:loft:0"]
    assert result.body_checks["f1"].volume == pytest.approx(tube_volume(2.0, 30.0), rel=2e-3)
    assert result.statuses["f1"].stats["freeform.stats.sections"] == 8
    assert [source.style for source in result.outputs["f1"].display] == ["section"]

    document = with_feature(
        document,
        "f2",
        "loft",
        {
            "path": "Z",
            "start": 30.0,
            "end": 58.0,
            "sectionCount": 10,
            "operation": "add",
            "targetBody": "f1",
        },
    )
    result = rebuild(document, session.environment(), job)
    assert result.statuses["f2"].state == "ok", result.statuses["f2"].error
    assert set(result.bodies) == {"f1"}
    assert result.body_checks["f1"].volume == pytest.approx(tube_volume(2.0, 58.0), rel=3e-3)
    tags = set(result.bodies["f1"].face_tags)
    assert {"f1:cap:start", "f2:cap:end"} <= tags


def test_loft_errors(session: Session, job: JobContext) -> None:
    vertices, faces = tube_scan(sigma=SIGMA)
    document = scan_document(session, vertices, faces, noise=SIGMA)
    cases: dict[str, dict[str, JsonValue]] = {
        "f1": {"path": "Z", "start": 30.0, "end": 10.0},
        "f2": {"path": "Z", "start": 10.0, "end": 80.0},
        "f3": {"path": "Z", "start": 10.0, "end": 20.0, "operation": "add"},
    }
    for feature_id, params in cases.items():
        document = with_feature(document, feature_id, "loft", params)
    statuses = rebuild(document, session.environment(), job).statuses
    codes = {key: status.error.code for key, status in statuses.items() if status.error}
    assert codes == {
        "f1": "freeform.invalidRange",
        "f2": "freeform.noSection",
        "f3": "cad.targetRequired",
    }


def test_feature_faces_returns_the_stored_triangles(session: Session, job: JobContext) -> None:
    field = height_field_scan(sigma=SIGMA)
    document = scan_document(session, field.vertices, field.faces, noise=SIGMA)
    faces = np.arange(0, 3000, 3, dtype=np.uint32)
    document = with_feature(document, "f1", "freeformPatch", {"faces": session.blobs.put(faces)})
    document = with_feature(document, "f2", "loft", {"path": "Z", "start": 0.0, "end": 1.0})
    session.commit(replace(document, next_id=3), "setup", job)
    stored = freeform_feature_faces(job, FeatureFacesParams(feature_id="f1"))
    assert stored.faces is not None
    np.testing.assert_array_equal(stored.faces, faces)
    assert freeform_feature_faces(job, FeatureFacesParams(feature_id="f2")).faces is None
    with pytest.raises(KernelError) as raised:
        freeform_feature_faces(job, FeatureFacesParams(feature_id="f9"))
    assert raised.value.code == "document.unknownFeature"


def test_loft_axis_reports_the_scan_extent(session: Session, job: JobContext) -> None:
    vertices, faces = tube_scan(sigma=SIGMA)
    session.commit(scan_document(session, vertices, faces, noise=SIGMA), "scan", job)
    axis = freeform_loft_axis(job, LoftAxisParams(path="Z"))
    assert axis.direction == (0.0, 0.0, 1.0)
    assert axis.low == pytest.approx(0.0, abs=0.1) and axis.high == pytest.approx(60.0, abs=0.1)
    ring = np.nonzero(np.abs(vertices[faces].mean(axis=1)[:, 2] - 20.0) < 2.0)[0]
    part = freeform_loft_axis(job, LoftAxisParams(path="Z", faces=ring.astype(np.uint32)))
    assert 17.0 < part.low < part.high < 23.0
    with pytest.raises(KernelError) as raised:
        freeform_loft_axis(job, LoftAxisParams(path="f7"))
    assert raised.value.code == "freeform.notAnAxis"
