"""Previews of solid features through `doc.preview`, as the tools call them."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.commands.doc import PreviewParams, doc_preview
from m2c_kernel.commands.scene import FetchParams, scene_fetch
from m2c_kernel.document.display import LinesPayload, MeshPayload
from m2c_kernel.document.ops import UpdateFeature
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.features.helpers import document, feature, rect, upstream_test_types

pytestmark = pytest.mark.occt

HOLES = [(15.0, 15.0, 5.0), (85.0, 15.0, 5.0), (15.0, 45.0, 5.0), (85.0, 45.0, 5.0)]


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    with upstream_test_types():
        yield


def _committed_plate(session: Session, job: JobContext) -> None:
    plate = rect("l1", 0, 0, 100, 60) | {"holes": HOLES}
    doc = document(
        feature("f1", "testSketch", rects=[plate]),
        feature("f2", "extrude", sketch="f1", extent={"type": "distance", "forward": 10.0}),
    )
    session.commit(replace(doc, revision=session.document.revision), "test", job)


def test_extrude_preview_with_display_is_fast(session: Session, job: JobContext) -> None:
    _committed_plate(session, job)
    extent = {"type": "distance", "forward": 12.0}
    op = UpdateFeature(id="f2", params=RawObject({"sketch": "f1", "extent": extent}))
    started = time.perf_counter()
    preview = doc_preview(job, PreviewParams(base_revision=session.document.revision, ops=[op]))
    fetched = scene_fetch(job, FetchParams(keys=[item.key for item in preview.items]))
    elapsed = time.perf_counter() - started

    assert preview.status is not None and preview.status.state == "ok"
    (body,) = preview.bodies
    assert body.volume == pytest.approx((6000 - 4 * np.pi * 25) * 12, abs=1e-3)
    assert elapsed < 0.5
    assert {item.style for item in preview.items} == {"previewBody", "bodyEdges"}
    mesh = next(p for p in fetched.payloads if isinstance(p, MeshPayload))
    lines = next(p for p in fetched.payloads if isinstance(p, LinesPayload))
    # Picking contract: face ids and edge face pairs index into the body's face tags.
    assert int(mesh.face_ids.max()) == len(body.face_tags) - 1
    assert lines.faces is not None and int(lines.faces.max()) < len(body.face_tags)
    top = body.face_tags.index("f2:cap:end")
    hole = body.face_tags.index("f2:side:l1h0")
    pairs = {tuple(sorted(pair)) for pair in lines.faces.tolist()}
    assert tuple(sorted((top, hole))) in pairs


def test_preview_reports_errors_without_bodies(session: Session, job: JobContext) -> None:
    _committed_plate(session, job)
    params = {"sketch": "f1", "extent": {"type": "distance", "forward": 0.0}}
    op = UpdateFeature(id="f2", params=RawObject(params))
    preview = doc_preview(job, PreviewParams(base_revision=session.document.revision, ops=[op]))
    assert preview.status is not None and preview.status.state == "error"
    assert preview.status.error is not None and preview.status.error.code == "cad.zeroLength"
    assert preview.bodies == ()
