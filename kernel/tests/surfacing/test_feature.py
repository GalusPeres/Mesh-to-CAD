"""The autoSurface feature in a rebuild, its STEP export and the `surfacing.preview` command."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.commands.surfacing import (
    FeatureFacesParams,
    PreviewParams,
    surfacing_feature_faces,
    surfacing_preview,
)
from m2c_kernel.document.ops import AddFeature, NewFeature
from m2c_kernel.document.rebuild import rebuild
from m2c_kernel.document.results import Body
from m2c_kernel.export.api import check_body, write_step
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue, RawObject
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.surfacing import shapes
from tests.surfacing.conftest import scan_document, with_feature

pytestmark = [pytest.mark.occt, pytest.mark.usefixtures("in_process_decimation")]

COARSE: dict[str, JsonValue] = {"detail": "coarse", "smoothing": "low"}


def test_closed_scan_gives_a_body(session: Session, job: JobContext, tmp_path: Path) -> None:
    scan = shapes.blob()
    document = with_feature(
        scan_document(session, scan.vertices, scan.faces, scan.sigma), "f1", "autoSurface", COARSE
    )
    result = rebuild(document, session.environment(), job)
    status = result.statuses["f1"]
    assert status.state == "ok", status.error
    stats = status.stats
    assert stats["patches"] == 1200 and stats["closed"] == 1.0
    assert stats["deviationRms"] is not None and stats["deviationRms"] < 2.0 * scan.sigma

    body = result.outputs["f1"].bodies.changed["f1"]
    assert isinstance(body, Body)
    assert len(body.face_tags) == 1200
    assert body.face_tags[0].startswith("f1:patch:")
    check = check_body(body)
    assert not check.blocking and check.closed and check.solids == 1 and check.volume > 0

    written, step = write_step(tmp_path / "blob.step", [("Blob", body)])
    assert step.passed, step
    assert written.bytes > 0 and (tmp_path / "blob.step").exists()


def test_open_scan_gives_a_construction_surface(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    centroids = scan.vertices[scan.faces].mean(axis=1)
    faces = scan.faces[centroids[:, 2] > -5.0]
    document = with_feature(
        scan_document(session, scan.vertices, faces, scan.sigma), "f1", "autoSurface", COARSE
    )
    result = rebuild(document, session.environment(), job)
    status = result.statuses["f1"]
    assert status.state == "warning"
    assert [issue.code for issue in status.issues] == ["surfacing.openSurface"]
    output = result.outputs["f1"]
    assert output.construction is not None and output.construction.surface is not None
    assert not output.bodies.changed
    assert {source.style for source in output.display} == {"patch", "constructionEdges"}


def test_selected_faces_only(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    centroids = scan.vertices[scan.faces].mean(axis=1)
    selected = np.flatnonzero(centroids[:, 0] > 0.0).astype(np.uint32)
    document = scan_document(session, scan.vertices, scan.faces, scan.sigma)
    params = {**COARSE, "faces": session.blobs.put(selected)}
    result = rebuild(
        with_feature(document, "f1", "autoSurface", params), session.environment(), job
    )
    status = result.statuses["f1"]
    assert status.state == "warning"
    assert [issue.code for issue in status.issues] == ["surfacing.openSurface"]


def test_preview_command(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    snapshot = session.commit(
        scan_document(session, scan.vertices, scan.faces, scan.sigma), "scan", job
    )
    op = AddFeature(feature=NewFeature(type="autoSurface", params=RawObject(dict(COARSE))))
    preview = surfacing_preview(job, PreviewParams(base_revision=snapshot.revision, ops=[op]))
    assert preview.status is not None and preview.status.state == "ok"
    assert len(preview.bodies) == 1 and preview.bodies[0].valid

    other = AddFeature(feature=NewFeature(type="primitiveBody", params=RawObject({})))
    with pytest.raises(KernelError) as raised:
        surfacing_preview(job, PreviewParams(base_revision=snapshot.revision, ops=[other]))
    assert raised.value.code == "surfacing.notAutoSurface"


def test_feature_faces(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    selected = np.arange(0, len(scan.faces), 2, dtype=np.uint32)
    document = scan_document(session, scan.vertices, scan.faces, scan.sigma)
    params: dict[str, JsonValue] = {**COARSE, "faces": session.blobs.put(selected)}
    document = with_feature(document, "f1", "autoSurface", params)
    document = with_feature(document, "f2", "autoSurface", COARSE)
    snapshot = session.commit(document, "features", job)
    stored = surfacing_feature_faces(job, FeatureFacesParams(feature_id="f1"))
    assert stored.faces is not None and np.array_equal(stored.faces, selected)
    assert snapshot.document.scan is not None and stored.scan_key == snapshot.document.scan.key
    assert surfacing_feature_faces(job, FeatureFacesParams(feature_id="f2")).faces is None
