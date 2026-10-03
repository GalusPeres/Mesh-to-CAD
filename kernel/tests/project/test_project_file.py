"""The `.m2c` container: round trip, damaged and hostile files, atomic saving."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.commands.mesh import (
    CommitImportParams,
    ImportParams,
    mesh_commit_import,
    mesh_import,
)
from m2c_kernel.document import project_file
from m2c_kernel.document.model import Document, DocumentSettings, Feature, Region, Regions
from m2c_kernel.document.project_file import PROJECT_VERSION, load_project, save_project
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import to_json
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session

UI_STATE = {"stage": "model", "camera": {"position": [1.0, 2.0, 3.0]}}


def build_project_document(session: Session, job: JobContext, stl: Path) -> Document:
    """A document with a scan, regions, a feature with a face set and changed settings."""
    report = mesh_import(job, ImportParams(path=str(stl)))
    mesh_commit_import(job, CommitImportParams(pending_id=report.pending_id, unit="mm"))
    scan = session.document.scan
    assert scan is not None
    labels = np.zeros(scan.face_count, dtype=np.uint16)
    labels[:200] = 1
    regions = Regions(
        labels=session.blobs.put(labels),
        items=(Region("r2", 1, "Deckel", "sphere", 0.02, 200, 12.5, 3),),
    )
    faces = session.blobs.put(np.arange(50, 250, dtype=np.uint32))
    feature = Feature("f1", "fit", "Kugel oben", False, {"faces": faces, "kind": "sphere"})
    document = replace(
        session.document,
        next_id=3,
        regions=regions,
        features=(feature,),
        settings=DocumentSettings(tolerance=0.15, snap_units="inch"),
    )
    session.commit(document, "setup", job)
    return session.document


def _json(document: Document) -> object:
    return to_json(replace(document, revision=0), Document)


def _blob_hashes(document: Document, blobs: BlobStore) -> dict[str, bytes]:
    return {ref: blobs.get(ref).tobytes() for ref in document.blob_refs()}


@pytest.fixture
def saved(session: Session, job: JobContext, sphere_stl: Path, tmp_path: Path) -> Path:
    document = build_project_document(session, job, sphere_stl)
    path = tmp_path / "halterung.m2c"
    save_project(path, document, UI_STATE, session.blobs)
    return path


def test_round_trip_keeps_the_document_and_every_blob(
    session: Session, saved: Path, tmp_path: Path
) -> None:
    fresh = BlobStore(tmp_path / "other-session" / "blobs")
    loaded = load_project(saved, fresh)
    assert _json(loaded.document) == _json(session.document)
    assert loaded.ui_state == UI_STATE
    original = _blob_hashes(session.document, session.blobs)
    assert _blob_hashes(loaded.document, fresh) == original
    assert len(original) == 4  # scan vertices and faces, region labels, the face set
    with zipfile.ZipFile(saved) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert {"manifest.json", "document.json", "ui.json"} <= names
    assert manifest["format"] == "mesh-to-cad-project"
    assert manifest["version"] == PROJECT_VERSION
    assert len(manifest["blobs"]) == len(original)


def test_scan_vertices_are_stored_as_float32_relative_to_the_origin(
    session: Session, saved: Path
) -> None:
    scan = session.document.scan
    assert scan is not None
    with zipfile.ZipFile(saved) as archive:
        stored = np.load(io.BytesIO(archive.read(f"blobs/{scan.vertices[5:]}.npy")))
    assert stored.dtype == np.float32
    assert np.abs(stored.mean(axis=0)).max() < 1.0


def test_saving_again_keeps_the_previous_file_as_backup(session: Session, saved: Path) -> None:
    previous = saved.read_bytes()
    save_project(saved, session.document, {"stage": "inspect"}, session.blobs)
    assert saved.with_name("halterung.m2c.bak").read_bytes() == previous
    assert load_project(saved, session.blobs).ui_state == {"stage": "inspect"}
    assert not list(saved.parent.glob(".*.tmp"))


def test_a_failure_while_saving_leaves_the_original_intact(
    session: Session, saved: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = saved.read_bytes()

    def fail(*_args: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(project_file, "replace_with_retry", fail)
    with pytest.raises(PermissionError):
        save_project(saved, session.document, None, session.blobs)
    assert saved.read_bytes() == previous
    assert not list(saved.parent.glob(".*.tmp"))


def test_a_failure_while_writing_blobs_leaves_the_original_intact(
    session: Session, saved: Path
) -> None:
    previous = saved.read_bytes()
    broken = replace(
        session.document,
        features=(Feature("f9", "fit", None, False, {"faces": "blob:" + "0" * 64}),),
    )
    with pytest.raises(FileNotFoundError):
        save_project(saved, broken, None, session.blobs)
    assert saved.read_bytes() == previous
    assert not list(saved.parent.glob(".*.tmp"))


def _rewrite(source: Path, target: Path, change: dict[str, bytes | None]) -> Path:
    """Copy a project, replacing (bytes), removing (None) or adding entries."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as copy:
        for name in original.namelist():
            if name not in change:
                copy.writestr(name, original.read(name))
        for name, data in change.items():
            if data is not None:
                copy.writestr(name, data)
    return target


def _expect(path: Path, code: str, blobs: BlobStore) -> KernelError:
    with pytest.raises(KernelError) as caught:
        load_project(path, blobs)
    assert caught.value.code == code
    return caught.value


def test_files_that_are_no_project_are_corrupt(tmp_path: Path, session: Session) -> None:
    garbage = tmp_path / "garbage.m2c"
    garbage.write_bytes(b"PK\x03\x04 not really a zip")
    _expect(garbage, "project.corrupt", session.blobs)
    other = tmp_path / "other.m2c"
    with zipfile.ZipFile(other, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "something-else", "version": 1}))
        archive.writestr("document.json", "{}")
    _expect(other, "project.corrupt", session.blobs)


@pytest.mark.parametrize(
    "change",
    [
        {"document.json": None},
        {"manifest.json": None},
        {"document.json": b"{not json"},
        {"document.json": json.dumps({"format": "mesh-to-cad-document", "version": 1}).encode()},
        {"ui.json": b"\xff\xfe"},
    ],
    ids=["no-document", "no-manifest", "broken-json", "no-document-body", "broken-ui"],
)
def test_incomplete_projects_are_corrupt(
    saved: Path, tmp_path: Path, session: Session, change: dict[str, bytes | None]
) -> None:
    _expect(_rewrite(saved, tmp_path / "broken.m2c", change), "project.corrupt", session.blobs)


def test_an_invalid_document_is_corrupt(saved: Path, tmp_path: Path, session: Session) -> None:
    with zipfile.ZipFile(saved) as archive:
        stored = json.loads(archive.read("document.json"))
    stored["document"]["settings"]["tolerance"] = "fine"
    broken = _rewrite(saved, tmp_path / "b.m2c", {"document.json": json.dumps(stored).encode()})
    _expect(broken, "project.corrupt", session.blobs)


def test_tampered_and_missing_blobs_are_detected(
    saved: Path, tmp_path: Path, session: Session
) -> None:
    with zipfile.ZipFile(saved) as archive:
        name = next(name for name in archive.namelist() if name.startswith("blobs/"))
        array = np.load(io.BytesIO(archive.read(name)))
    changed = array.copy()
    changed.flat[0] = changed.flat[1]
    buffer = io.BytesIO()
    np.save(buffer, changed)
    tampered = _rewrite(saved, tmp_path / "t.m2c", {name: buffer.getvalue()})
    _expect(tampered, "project.corrupt", session.blobs)
    missing = _rewrite(saved, tmp_path / "m.m2c", {name: None})
    _expect(missing, "project.corrupt", session.blobs)


def test_a_blob_larger_than_its_manifest_entry_is_not_unpacked(
    saved: Path, tmp_path: Path, session: Session
) -> None:
    with zipfile.ZipFile(saved) as archive:
        name = next(name for name in archive.namelist() if name.startswith("blobs/"))
    bomb = np.zeros(4_000_000, dtype=np.uint8)
    buffer = io.BytesIO()
    np.save(buffer, bomb)
    bombed = _rewrite(saved, tmp_path / "bomb.m2c", {name: buffer.getvalue()})
    _expect(bombed, "project.corrupt", session.blobs)


HOSTILE_NAMES = ["../outside.txt", "blobs/../../outside.npy", "C:/outside.npy", "/a.npy", "x.json"]


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_entries_outside_the_layout_are_rejected(
    saved: Path, tmp_path: Path, session: Session, name: str
) -> None:
    hostile = _rewrite(saved, tmp_path / "h.m2c", {name: b"x"})
    _expect(hostile, "project.corrupt", session.blobs)
    assert not (tmp_path / "outside.txt").exists()
    assert not (tmp_path.parent / "outside.npy").exists()


def test_a_newer_version_is_refused(saved: Path, tmp_path: Path, session: Session) -> None:
    with zipfile.ZipFile(saved) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["version"] = PROJECT_VERSION + 1
    newer = _rewrite(saved, tmp_path / "n.m2c", {"manifest.json": json.dumps(manifest).encode()})
    error = _expect(newer, "project.unsupportedVersion", session.blobs)
    assert error.params == {"version": PROJECT_VERSION + 1, "supported": PROJECT_VERSION}


def test_migrations_run_for_older_files(
    saved: Path, tmp_path: Path, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pretend the current version is 2: a version 1 file passes through MIGRATIONS[1]."""
    seen: list[int] = []

    def to_v2(document: dict[str, object]) -> dict[str, object]:
        seen.append(1)
        settings = dict(document["settings"])  # type: ignore[call-overload]
        settings["tolerance"] = 0.3
        return {**document, "settings": settings}

    monkeypatch.setattr(project_file, "PROJECT_VERSION", 2)
    monkeypatch.setitem(project_file.MIGRATIONS, 1, to_v2)
    loaded = load_project(saved, session.blobs)
    assert seen == [1]
    assert loaded.document.settings.tolerance == 0.3
