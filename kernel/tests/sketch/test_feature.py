"""The sketch commands and the sketch feature in a session: commit, rebuild, deviation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.codes.sketch import IssueCode
from m2c_kernel.commands.doc import ApplyParams, doc_apply
from m2c_kernel.commands.sketch import (
    AutoFitParams,
    FitEntityParams,
    SectionParams,
    sketch_auto_fit,
    sketch_fit_entity,
    sketch_section,
)
from m2c_kernel.document.model import Document, Scan, ScanSource
from m2c_kernel.document.ops import AddFeature, NewFeature, UpdateFeature
from m2c_kernel.document.rebuild import rebuild
from m2c_kernel.geometry import Matrix4
from m2c_kernel.protocol.wire import RawObject, to_json
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from m2c_kernel.sketch.params import (
    AxisNormalSource,
    PlanarSection,
    RotationalSection,
    SketchParams,
)
from tests.sketch.conftest import PLATE_SPEC, noisy_plate

pytestmark = pytest.mark.occt


def _plate_document(session: Session) -> Document:
    scan = noisy_plate(0.02)
    origin = np.round(scan.vertices.mean(axis=0), 1)
    vertices = session.blobs.put((scan.vertices - origin).astype(np.float32))
    faces = session.blobs.put(scan.faces.astype(np.uint32))
    return replace(
        Document.empty(),
        scan=Scan(
            key="scan:plate",
            source=ScanSource("plate.stl", "0", "mm"),
            vertices=vertices,
            faces=faces,
            synthetic=None,
            vertex_count=len(scan.vertices),
            face_count=len(scan.faces),
            origin=(float(origin[0]), float(origin[1]), float(origin[2])),
            noise=0.02,
        ),
    )


@pytest.fixture
def plate_session(session: Session, job: JobContext) -> Session:
    session.commit(_plate_document(session), "import", job)
    return session


def _add_sketch(session: Session, job: JobContext, params: SketchParams) -> str:
    feature = NewFeature(type="sketch", params=RawObject(to_json(params, SketchParams)))
    ops = [AddFeature(feature=feature)]
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=ops, label="sketch"))
    return session.document.features[-1].id


def test_section_command_returns_the_cut_in_the_sketch_frame(
    plate_session: Session, job: JobContext
) -> None:
    result = sketch_section(job, SectionParams(section=PLATE_SPEC))
    assert result.frame.normal == pytest.approx((0, 0, 1))
    assert result.frame.origin == pytest.approx((0, 0, 0))
    assert result.closed.count(True) == 3
    assert result.folded is None
    outer = max(result.polylines, key=len)
    assert np.ptp(outer[:, 0]) == pytest.approx(100.0, abs=0.2)
    assert 0.01 < result.noise < 0.03
    assert result.suggested_tolerance == pytest.approx(max(6 * result.noise, 0.05))


def test_committed_sketch_builds_profiles_and_display(
    plate_session: Session, job: JobContext
) -> None:
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC)))
    assert fitted.profile.closed
    feature_id = _add_sketch(plate_session, job, fitted.sketch)
    snapshot = plate_session.snapshot("current", job)
    status = snapshot.status.features[feature_id]
    assert status.state == "ok", status
    assert status.stats["sketch.loops"] == 3
    styles = sorted(item.style for item in snapshot.scene.items if item.owner == feature_id)
    assert styles == ["sectionPoints", "sketch"]
    output = plate_session.built(job).result.outputs[feature_id]
    assert output.sketch is not None
    assert len(output.sketch.profile_faces) == 1


def test_open_profile_is_reported_with_gap_positions(
    plate_session: Session, job: JobContext
) -> None:
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC))).sketch
    removed = fitted.entities[1].id
    feature_id = _add_sketch(
        plate_session,
        job,
        replace(fitted, entities=[e for e in fitted.entities if e.id != removed]),
    )
    status = plate_session.snapshot("current", job).status.features[feature_id]
    issue = next(i for i in status.issues if i.code == IssueCode.PROFILE_OPEN)
    assert issue.params["count"] == 2
    gaps = np.array(issue.params["gaps"])
    assert gaps.shape == (2, 3)
    assert np.allclose(gaps[:, 2], 0.0)


def test_sketch_deviates_from_the_scan_after_the_alignment_moves(
    plate_session: Session, job: JobContext
) -> None:
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC)))
    feature_id = _add_sketch(plate_session, job, fitted.sketch)
    environment = plate_session.environment()

    def moved(_document: Document, _job: JobContext) -> Matrix4:
        return (1, 0, 0, 0.8, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)

    unchanged = rebuild(plate_session.document, environment, job).statuses[feature_id]
    assert unchanged.state == "ok"
    assert (unchanged.stats["sketch.deviation"] or 0) < 0.05

    shifted = rebuild(plate_session.document, replace(environment, evaluate_alignment=moved), job)
    status = shifted.statuses[feature_id]
    assert status.state == "warning"
    issue = next(i for i in status.issues if i.code == IssueCode.DEVIATES_FROM_SCAN)
    assert issue.params["max"] == pytest.approx(0.8, abs=0.05)


def test_refit_and_fit_entity_commands(plate_session: Session, job: JobContext) -> None:
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC)))
    refitted = sketch_auto_fit(job, AutoFitParams(sketch=fitted.sketch, refit=True))
    assert [e.id for e in refitted.sketch.entities] == [e.id for e in fitted.sketch.entities]
    assert all(f.passed for f in refitted.fits)
    section = sketch_section(job, SectionParams(section=PLATE_SPEC))
    outer = max(section.polylines, key=len).astype(np.float64)
    painted = outer[(outer[:, 1] < -29.5) & (np.abs(outer[:, 0]) < 30)]
    added = sketch_fit_entity(
        job, FitEntityParams(sketch=fitted.sketch, points=painted, kind="line")
    )
    assert added.max_distance < added.tolerance
    assert added.entity not in {e.id for e in fitted.sketch.entities}


def test_editing_the_sketch_updates_the_feature(plate_session: Session, job: JobContext) -> None:
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC))).sketch
    feature_id = _add_sketch(plate_session, job, fitted)
    holes_removed = replace(fitted, entities=[e for e in fitted.entities if e.type != "circle"])
    op = UpdateFeature(id=feature_id, params=RawObject(to_json(holes_removed, SketchParams)))
    doc_apply(
        job, ApplyParams(base_revision=plate_session.document.revision, ops=[op], label="edit")
    )
    status = plate_session.snapshot("current", job).status.features[feature_id]
    assert status.stats["sketch.loops"] == 1


def test_axis_references_of_planes_and_rotational_sections() -> None:
    from m2c_kernel.features.types.sketch import sketch_references

    planar = PlanarSection(plane=AxisNormalSource(axis="f3"))
    assert sketch_references(SketchParams(section=planar)) == ("f3",)
    assert sketch_references(SketchParams(section=RotationalSection(axis="Z"))) == ()
    assert sketch_references(SketchParams(section=RotationalSection(axis="f7"))) == ("f7",)
