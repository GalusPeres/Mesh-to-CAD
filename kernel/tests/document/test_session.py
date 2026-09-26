"""Commits, undo and redo through revisions, persistence and blob collection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.commands.doc import ApplyParams, PreviewParams, doc_apply, doc_preview
from m2c_kernel.commands.mesh import (
    CommitImportParams,
    ImportParams,
    mesh_commit_import,
    mesh_import,
    propose_tolerance,
)
from m2c_kernel.document.model import DocumentSettings
from m2c_kernel.document.ops import SetSettings
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.lock import SessionBusyError, is_owned
from m2c_kernel.session.session import Session
from tests.conftest import RecordingEvents


def _import(job: JobContext, path: Path) -> int:
    report = mesh_import(job, ImportParams(path=str(path)))
    return mesh_commit_import(
        job, CommitImportParams(pending_id=report.pending_id, unit="mm")
    ).revision


def test_a_new_session_starts_with_an_empty_revision(session: Session) -> None:
    assert session.document.revision == 0
    assert session.document.scan is None


def test_import_commits_a_revision_and_emits_the_document(
    session: Session, job: JobContext, events: RecordingEvents, sphere_stl: Path
) -> None:
    assert _import(job, sphere_stl) == 1
    scan = session.document.scan
    assert scan is not None
    assert scan.face_count == 5120
    assert scan.noise is not None and 0.005 < scan.noise < 0.05
    name, data = events.events[-1]
    assert name == "documentChanged"
    assert isinstance(data, dict) and data["cause"] == "commit"


def test_checkout_moves_between_revisions(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    session.checkout(0, job)
    assert session.document.scan is None
    session.checkout(1, job)
    assert session.document.scan is not None


def test_a_commit_after_undo_drops_the_redo_revisions(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    session.checkout(0, job)
    settings = SetSettings(settings=DocumentSettings(tolerance=0.2))
    revision = doc_apply(
        job, ApplyParams(base_revision=0, ops=[settings], label="settings")
    ).revision
    assert revision == 2
    assert session.revisions.numbers() == [0, 2]
    with pytest.raises(KernelError) as caught:
        session.checkout(1, job)
    assert caught.value.code == "document.revisionGone"


def test_stale_base_revisions_are_rejected(session: Session, job: JobContext) -> None:
    settings = SetSettings(settings=DocumentSettings(tolerance=0.2))
    with pytest.raises(KernelError) as caught:
        doc_apply(job, ApplyParams(base_revision=5, ops=[settings], label="x"))
    assert caught.value.code == "document.staleRevision"


def test_preview_does_not_commit(session: Session, job: JobContext) -> None:
    settings = SetSettings(settings=DocumentSettings(tolerance=0.2))
    result = doc_preview(job, PreviewParams(base_revision=0, ops=[settings]))
    assert result.feature_id is None
    assert session.document.revision == 0
    assert session.revisions.numbers() == [0]


def test_head_and_document_survive_a_restart(
    tmp_path: Path, events: RecordingEvents, sphere_stl: Path
) -> None:
    directory = tmp_path / "restart"
    first = Session.open(directory, events)
    _import(JobContext.detached(first), sphere_stl)
    first.checkout(0, JobContext.detached(first))
    first.close()

    second = Session.open(directory, events)
    try:
        assert second.document.revision == 0
        second.checkout(1, JobContext.detached(second))
        assert second.document.scan is not None
    finally:
        second.close()


def test_the_lock_marks_the_session_as_owned(tmp_path: Path, events: RecordingEvents) -> None:
    directory = tmp_path / "locked"
    opened = Session.open(directory, events)
    try:
        assert is_owned(directory)
        with pytest.raises(SessionBusyError):
            Session.open(directory, events)
    finally:
        opened.close()
    assert not is_owned(directory)


def test_blobs_of_dropped_revisions_are_collected(
    session: Session, job: JobContext, sphere_stl: Path
) -> None:
    _import(job, sphere_stl)
    scan = session.document.scan
    assert scan is not None
    session.checkout(0, job)
    settings = SetSettings(settings=DocumentSettings(tolerance=0.2))
    doc_apply(job, ApplyParams(base_revision=0, ops=[settings], label="settings"))
    assert not session.blobs.contains(scan.vertices)
    assert not session.blobs.contains(scan.faces)


def test_blob_store_deduplicates_equal_arrays(session: Session) -> None:
    array = np.arange(10, dtype=np.float32)
    assert session.blobs.put(array) == session.blobs.put(array.copy())
    stored = session.blobs.get(session.blobs.put(array))
    assert not stored.flags.writeable


@pytest.mark.parametrize(
    ("noise", "expected"), [(None, 0.1), (0.01, 0.05), (0.036, 0.1), (0.07, 0.2)]
)
def test_tolerance_proposal_from_noise(noise: float | None, expected: float) -> None:
    assert propose_tolerance(noise) == expected


def test_settings_are_part_of_the_document(session: Session, job: JobContext) -> None:
    settings = replace(DocumentSettings(), tolerance=0.25, snap_units="inch")
    doc_apply(job, ApplyParams(base_revision=0, ops=[SetSettings(settings=settings)], label="s"))
    assert session.document.settings.snap_units == "inch"
