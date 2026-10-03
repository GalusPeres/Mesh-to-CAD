"""`project.new`, `project.save` and `project.load` on a session and through the protocol."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from m2c_kernel.commands.project import (
    LoadParams,
    NewParams,
    SaveParams,
    project_load,
    project_new,
    project_save,
)
from m2c_kernel.document.model import Document
from m2c_kernel.document.project_file import load_project
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import to_json
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.conftest import RecordingEvents
from tests.kernel_process import KernelProcess
from tests.project.test_project_file import UI_STATE, build_project_document

FIXTURES = Path(__file__).parent / "fixtures"


def _json(document: Document) -> object:
    return to_json(replace(document, revision=0), Document)


def test_load_makes_the_file_the_rebuilt_head(
    session: Session,
    job: JobContext,
    events: RecordingEvents,
    sphere_stl: Path,
    tmp_path: Path,
) -> None:
    original = build_project_document(session, job, sphere_stl)
    path = tmp_path / "halterung.m2c"
    saved = project_save(job, SaveParams(path=str(path), ui=UI_STATE))
    assert saved.file_name == "halterung.m2c"
    assert saved.revision == original.revision

    project_new(job, NewParams())
    assert session.document.scan is None

    loaded = project_load(job, LoadParams(path=str(path)))
    assert loaded.ui == UI_STATE
    assert loaded.file_name == "halterung.m2c"
    assert session.document.revision == loaded.revision == session.revisions.head
    assert _json(session.document) == _json(original)
    name, data = events.events[-1]
    assert name == "documentChanged"
    assert isinstance(data, dict)
    assert data["revision"] == loaded.revision
    assert data["scene"]["scan"]["faceCount"] == 5120
    assert data["status"]["features"]["f1"]["state"] in {"ok", "warning", "error"}


def test_a_restarted_kernel_keeps_the_loaded_project(
    session: Session, job: JobContext, events: RecordingEvents, sphere_stl: Path, tmp_path: Path
) -> None:
    original = build_project_document(session, job, sphere_stl)
    path = tmp_path / "p.m2c"
    project_save(job, SaveParams(path=str(path)))
    project_new(job, NewParams())
    project_load(job, LoadParams(path=str(path)))
    directory = session.directory
    session.close()
    reopened = Session.open(directory, events)
    try:
        assert _json(reopened.document) == _json(original)
    finally:
        reopened.close()


def test_new_starts_an_empty_document(session: Session, job: JobContext, sphere_stl: Path) -> None:
    build_project_document(session, job, sphere_stl)
    result = project_new(job, NewParams())
    assert result.revision == session.document.revision
    assert session.document.scan is None and session.document.features == ()


def test_errors_name_the_file(session: Session, job: JobContext, tmp_path: Path) -> None:
    with pytest.raises(KernelError) as missing:
        project_load(job, LoadParams(path=str(tmp_path / "gone.m2c")))
    assert missing.value.code == "project.fileNotFound"
    assert missing.value.params == {"fileName": "gone.m2c"}
    broken = tmp_path / "broken.m2c"
    broken.write_bytes(b"nothing")
    with pytest.raises(KernelError) as corrupt:
        project_load(job, LoadParams(path=str(broken)))
    assert corrupt.value.code == "project.corrupt"
    assert corrupt.value.params == {"fileName": "broken.m2c"}
    with pytest.raises(KernelError) as unwritable:
        project_save(job, SaveParams(path=str(tmp_path / "missing-folder" / "p.m2c")))
    assert unwritable.value.code == "project.saveFailed"


def test_the_version_1_fixture_still_loads(session: Session, job: JobContext) -> None:
    """A stored file of every released version must keep loading (ARCHITECTURE.md 4.10).

    Regenerate with `M2C_WRITE_FIXTURES=1` only when the fixture itself is broken, never
    to make a format change pass.
    """
    fixture = FIXTURES / "v1.m2c"
    if os.environ.get("M2C_WRITE_FIXTURES") == "1" or not fixture.exists():
        _write_v1_fixture(session, job, fixture)
    loaded = load_project(fixture, session.blobs)
    document = loaded.document
    assert document.scan is not None
    assert document.scan.face_count == 320
    assert document.scan.source.file_name == "fixture_sphere.stl"
    assert [item.id for item in document.regions.items] == ["r2"]
    assert document.features[0].name == "Kugel oben"
    assert document.settings.tolerance == 0.15
    assert document.settings.snap_units == "inch"
    assert loaded.ui_state == UI_STATE


def _write_v1_fixture(session: Session, job: JobContext, fixture: Path) -> None:
    from tests.synthetic import sphere_scan, write_binary_stl

    fixture.parent.mkdir(parents=True, exist_ok=True)
    stl_folder = session.directory.parent
    vertices, faces = sphere_scan(radius=20.0, subdivisions=2, sigma=0.02)
    stl = write_binary_stl(stl_folder / "fixture_sphere.stl", vertices, faces)
    build_project_document(session, job, stl)
    project_save(job, SaveParams(path=str(fixture), ui=UI_STATE))
    fixture.with_name(f"{fixture.name}.bak").unlink(missing_ok=True)


def test_file_methods_are_main_only_and_work_through_the_protocol(
    kernel: KernelProcess, sphere_stl: Path, tmp_path: Path
) -> None:
    path = tmp_path / "p.m2c"
    assert kernel.call("project.save", {"path": str(path)}).error_code == "kernel.notAllowed"
    report = kernel.call("mesh.import", {"path": str(sphere_stl)}, origin="main").result
    kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"})
    params = {"path": str(path), "ui": {"stage": "align"}}
    saved = kernel.call("project.save", params, origin="main")
    assert saved.result == {"fileName": "p.m2c", "revision": 1}
    assert kernel.call("project.new").ok
    loaded = kernel.call("project.load", {"path": str(path)}, origin="main").result
    assert loaded["ui"] == {"stage": "align"}
    snapshot = kernel.call("doc.get").result
    assert snapshot["revision"] == loaded["revision"]
    assert snapshot["document"]["scan"]["faceCount"] == 5120
