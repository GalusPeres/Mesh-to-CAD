"""Import and preparation commands on a session: units, dry runs, commits and remapping."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.commands.mesh import (
    CommitImportParams,
    DecimateParams,
    DeleteFacesParams,
    FillHolesParams,
    ImportParams,
    ImportReport,
    InspectParams,
    RemoveSmallPartsParams,
    RepairParams,
    SetSmoothingParams,
    mesh_commit_import,
    mesh_decimate,
    mesh_delete_faces,
    mesh_fill_holes,
    mesh_import,
    mesh_inspect,
    mesh_remove_small_parts,
    mesh_repair,
    mesh_set_smoothing,
    propose_tolerance,
)
from m2c_kernel.document.model import Feature, Region, Regions
from m2c_kernel.mesh.normals import face_normals
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.conftest import RecordingEvents
from tests.mesh.dirty import DEBRIS_PARTS, dirty_box_scan
from tests.synthetic import box_scan, sphere_scan, write_binary_stl


def _import(job: JobContext, path: Path, reduce_to: int | None = None) -> int:
    report = mesh_import(job, ImportParams(path=str(path)))
    params = CommitImportParams(pending_id=report.pending_id, unit="mm", reduce_to=reduce_to)
    return mesh_commit_import(job, params).revision


def _scan_points(session: Session) -> np.ndarray:
    scan = session.document.scan
    assert scan is not None
    return session.blobs.get(scan.vertices).astype(np.float64) + np.asarray(scan.origin)


@pytest.fixture(scope="module")
def dirty_stl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    scan = dirty_box_scan()
    folder = tmp_path_factory.mktemp("dirty")
    return write_binary_stl(folder / "dirty_box.stl", scan.mesh.vertices, scan.mesh.faces)


def test_import_report_gives_noise_and_tolerance_per_unit(
    job: JobContext, sphere_stl: Path
) -> None:
    report = mesh_import(job, ImportParams(path=str(sphere_stl)))
    assert report.file_name == "sphere.stl"
    assert report.face_count == 5120
    assert report.counts["mergedVertices"] == 3 * 5120 - report.vertex_count
    assert report.suggested_unit == "mm"
    assert not report.reduction_required
    assert np.allclose(np.subtract(report.bounds_max, report.bounds_min), 40.0, atol=0.2)
    noise = report.noise["mm"]
    assert noise is not None and 0.01 < noise < 0.04
    assert report.proposed_tolerance["mm"] == propose_tolerance(noise)
    assert set(report.noise) == {"mm", "cm", "m", "in"}
    for unit, value in report.noise.items():
        assert report.proposed_tolerance[unit] == propose_tolerance(value)


def test_a_file_in_metres_is_recognised_and_measured_at_its_scale(
    job: JobContext, tmp_path: Path
) -> None:
    vertices, faces = sphere_scan(radius=20.0, subdivisions=4, sigma=0.02)
    in_mm = mesh_import(
        job, ImportParams(path=str(write_binary_stl(tmp_path / "a.stl", vertices, faces)))
    )
    in_m = mesh_import(
        job, ImportParams(path=str(write_binary_stl(tmp_path / "b.stl", vertices / 1000, faces)))
    )
    assert in_m.suggested_unit == "m"
    assert in_m.noise["m"] == pytest.approx(in_mm.noise["mm"], rel=0.05)
    assert in_m.proposed_tolerance["m"] == in_mm.proposed_tolerance["mm"]


def test_inch_import_scales_by_exactly_25_4(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    report: ImportReport = mesh_import(job, ImportParams(path=str(sphere_stl)))
    mesh_commit_import(job, CommitImportParams(pending_id=report.pending_id, unit="in"))
    scan = session.document.scan
    assert scan is not None and scan.source.import_unit == "in"
    points = _scan_points(session)
    size = points.max(axis=0) - points.min(axis=0)
    expected = (np.asarray(report.bounds_max) - np.asarray(report.bounds_min)) * 25.4
    np.testing.assert_allclose(size, expected, rtol=0, atol=2e-5 * 25.4 * 40)
    assert scan.noise == report.noise["in"]
    assert session.document.settings.tolerance == report.proposed_tolerance["in"]


def test_import_repairs_the_scan_and_records_the_counts(
    session: Session, job: JobContext, dirty_stl: Path
) -> None:
    _import(job, dirty_stl)
    scan = session.document.scan
    assert scan is not None
    counts = scan.operations[0].counts
    assert scan.operations[0].op == "import"
    assert counts["degenerateFaces"] == 25
    assert counts["duplicateFaces"] == 40
    assert counts["removedParts"] == DEBRIS_PARTS
    assert counts["flippedFaces"] > 0
    report = mesh_inspect(job, InspectParams())
    assert report.inconsistent_edges == 0
    assert report.boundary_loops == 3
    assert report.components == 1
    assert report.volume is None and not report.watertight


def test_a_large_scan_must_be_reduced(session: Session, job: JobContext, sphere_stl: Path) -> None:
    report = mesh_import(job, ImportParams(path=str(sphere_stl)))
    reduced = mesh_commit_import(
        job, CommitImportParams(pending_id=report.pending_id, unit="mm", reduce_to=2_000)
    )
    scan = session.document.scan
    assert scan is not None and scan.face_count <= 2_000
    assert reduced.counts["facesBefore"] == 5120
    with pytest.raises(KernelError) as unknown:
        mesh_commit_import(job, CommitImportParams(pending_id=report.pending_id, unit="mm"))
    assert unknown.value.code == "mesh.unknownImport"


def test_dry_runs_never_create_a_revision(
    session: Session, job: JobContext, events: RecordingEvents, dirty_stl: Path
) -> None:
    _import(job, dirty_stl)
    head = session.document.revision
    emitted = len(events.events)
    results = [
        mesh_repair(job, RepairParams(dry_run=True)),
        mesh_remove_small_parts(job, RemoveSmallPartsParams(min_faces=100_000, dry_run=True)),
        mesh_fill_holes(job, FillHolesParams(max_perimeter=30.0, dry_run=True)),
        mesh_decimate(job, DecimateParams(target_faces=10_000, dry_run=True)),
    ]
    assert all(result.revision is None for result in results)
    assert session.document.revision == head
    assert session.revisions.head == head
    assert len(events.events) == emitted
    holes = results[2]
    assert holes.changed and holes.counts["filledHoles"] == 3
    assert results[3].counts["facesAfter"] == 10_000


def test_filling_holes_commits_synthetic_faces(
    session: Session, job: JobContext, dirty_stl: Path
) -> None:
    _import(job, dirty_stl)
    before = session.document.scan
    assert before is not None
    result = mesh_fill_holes(job, FillHolesParams(max_perimeter=30.0))
    scan = session.document.scan
    assert scan is not None and result.revision == session.document.revision
    assert scan.key != before.key
    assert scan.operations[-1].op == "fillHoles"
    assert scan.synthetic is not None
    synthetic = session.blobs.get(scan.synthetic)
    assert int(synthetic.sum()) == result.counts["addedFaces"]
    assert (synthetic[: before.face_count] == 0).all()
    assert mesh_inspect(job, InspectParams()).watertight


def test_a_step_that_changes_nothing_does_not_commit(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    head = session.document.revision
    result = mesh_repair(job, RepairParams())
    assert not result.changed and result.revision is None
    assert session.document.revision == head


def test_deleting_faces_carries_face_sets_and_regions_over(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    scan = session.document.scan
    assert scan is not None
    blobs = session.blobs
    kept_set = blobs.put(np.arange(500, dtype=np.uint32))
    labels = np.zeros(scan.face_count, dtype=np.uint16)
    labels[:500] = 1
    labels[1000:1500] = 2
    regions = Regions(
        labels=blobs.put(labels),
        items=(
            Region("r1", 1, None, "plane", None, 500, 1.0, 0),
            Region("r2", 2, None, "plane", None, 500, 1.0, 1),
        ),
    )
    feature = Feature("f1", "fit", None, False, {"faces": kept_set, "kind": "sphere"})
    document = replace(session.document, regions=regions, features=(feature,), next_id=2)
    session.commit(document, "setup", job)

    deleted = np.r_[np.arange(100), np.arange(1000, 1500)].astype(np.uint32)
    result = mesh_delete_faces(job, DeleteFacesParams(faces=deleted, scan_key=scan.key))
    assert result.counts == {"deletedFaces": 600}
    document = session.document
    assert document.scan is not None and document.scan.face_count == scan.face_count - 600
    params = document.features[0].params
    assert isinstance(params, dict)
    assert blobs.get(str(params["faces"])).tolist() == list(range(400))
    assert [item.id for item in document.regions.items] == ["r1"]
    region = document.regions.items[0]
    assert region.face_count == 400
    new_labels = blobs.get(str(document.regions.labels))
    assert (new_labels[:400] == 1).all() and (new_labels[400:] == 0).all()
    points = _scan_points(session)
    _, areas = face_normals(points, blobs.get(document.scan.faces).astype(np.int64))
    assert region.area == pytest.approx(float(areas[:400].sum()))

    with pytest.raises(KernelError) as stale:
        mesh_delete_faces(job, DeleteFacesParams(faces=deleted[:1], scan_key=scan.key))
    assert stale.value.code == "mesh.staleSelection"


def test_region_labels_survive_reduction(session: Session, job: JobContext, tmp_path: Path) -> None:
    vertices, faces = box_scan(max_edge=0.8)
    _import(job, write_binary_stl(tmp_path / "box.stl", vertices, faces))
    scan = session.document.scan
    assert scan is not None
    labels = _side_labels(session)
    items = tuple(
        Region(f"r{label}", label, None, "plane", None, int((labels == label).sum()), 1.0, label)
        for label in range(1, 7)
    )
    regions = Regions(labels=session.blobs.put(labels), items=items)
    session.commit(replace(session.document, regions=regions), "regions", job)

    mesh_decimate(job, DecimateParams(target_faces=8_000))
    reduced = session.document
    assert reduced.scan is not None and reduced.scan.face_count <= 8_000
    carried = session.blobs.get(str(reduced.regions.labels))
    truth = _side_labels(session)
    for label in range(1, 7):
        union = np.count_nonzero((carried == label) | (truth == label))
        overlap = np.count_nonzero((carried == label) & (truth == label))
        assert overlap / union >= 0.95, label


def _side_labels(session: Session) -> np.ndarray:
    """Label 1-6 per face from the side of the box its normal points to."""
    scan = session.document.scan
    assert scan is not None
    faces = session.blobs.get(scan.faces).astype(np.int64)
    normals, _ = face_normals(_scan_points(session), faces)
    axis = np.abs(normals).argmax(axis=1)
    positive = normals[np.arange(len(normals)), axis] > 0
    return (1 + 2 * axis + positive).astype(np.uint16)


def test_smoothing_is_a_display_setting(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    scan = session.document.scan
    assert scan is not None
    result = mesh_set_smoothing(job, SetSmoothingParams(iterations=5))
    smoothed = session.document.scan
    assert smoothed is not None and result.revision is not None
    assert smoothed.display_smoothing == 5
    assert smoothed.vertices == scan.vertices and smoothed.key == scan.key
    assert mesh_set_smoothing(job, SetSmoothingParams(iterations=5)).revision is None


def test_preparation_without_a_scan_is_refused(job: JobContext) -> None:
    with pytest.raises(KernelError) as caught:
        mesh_repair(job, RepairParams(dry_run=True))
    assert caught.value.code == "mesh.noScan"
