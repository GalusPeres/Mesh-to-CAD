r"""The kernel's top-level state: one document with its history in a session directory.

Layout of a session directory (`%LOCALAPPDATA%\\Mesh-to-CAD\\sessions\\<id>`):

    session.lock        held while a kernel owns the session
    session.json        pid and start time of that kernel
    head.json           checked-out revision and next revision number
    revisions/<n>.json  document snapshots
    blobs/<sha>.npy     arrays referenced by the snapshots

Every document change goes through `commit`: rebuild, persist, emit
`documentChanged`. Nothing else replaces the current document.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from m2c_kernel.document.display import SceneManifest, SceneStore, build_scene
from m2c_kernel.document.model import DOCUMENT_FORMAT, DOCUMENT_VERSION, Document
from m2c_kernel.document.rebuild import (
    MeshProvider,
    RebuildEnvironment,
    RebuildResult,
    ResultCache,
    rebuild,
)
from m2c_kernel.document.results import BodyInfo, DisplaySource
from m2c_kernel.document.snapshot import ChangeCause, DocumentSnapshot, DocumentStatus
from m2c_kernel.features.registry import FeatureTypeSpec, load_feature_types
from m2c_kernel.mesh.load import PendingImport
from m2c_kernel.protocol.wire import from_json, to_json
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.lock import SessionLock
from m2c_kernel.session.revisions import RevisionStore

log = logging.getLogger(__name__)


class EventSink(Protocol):
    def emit_event(self, event: str, data: Any, buffers: Sequence[np.ndarray] = ()) -> None: ...


@dataclass(frozen=True)
class BuiltDocument:
    """A document together with its rebuild result and scene."""

    document: Document
    label: str
    result: RebuildResult
    status: DocumentStatus
    scene: SceneManifest


class Session:
    def __init__(self, directory: Path, events: EventSink, lock: SessionLock | None) -> None:
        self.directory = directory
        self._events = events
        self._lock = lock
        self.blobs = BlobStore(directory / "blobs")
        self.revisions = RevisionStore(directory)
        self.results = ResultCache()
        self.meshes = MeshProvider(self.blobs)
        self.scene = SceneStore()
        self.pending_imports: dict[str, PendingImport] = {}
        self._document, self._label = self._load_head()
        self._built: BuiltDocument | None = None

    @classmethod
    def open(cls, directory: Path, events: EventSink) -> Session:
        """Open or create a session directory and take its lock."""
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory, events, SessionLock.acquire(directory))

    @property
    def document(self) -> Document:
        return self._document

    @property
    def feature_types(self) -> Mapping[str, FeatureTypeSpec]:
        return load_feature_types()

    def environment(self) -> RebuildEnvironment:
        from m2c_kernel.alignment.api import evaluate_alignment

        return RebuildEnvironment(
            blobs=self.blobs,
            results=self.results,
            meshes=self.meshes,
            feature_types=self.feature_types,
            evaluate_alignment=evaluate_alignment,
        )

    def built(self, job: JobContext) -> BuiltDocument:
        """The current document with its rebuild result (rebuilt on first use)."""
        if self._built is None or self._built.document is not self._document:
            self._built = self._build(self._document, self._label, job)
        return self._built

    def snapshot(self, cause: ChangeCause, job: JobContext) -> DocumentSnapshot:
        built = self.built(job)
        return DocumentSnapshot(
            revision=built.document.revision,
            cause=cause,
            label=built.label,
            document=built.document,
            status=built.status,
            scene=built.scene,
        )

    def commit(self, document: Document, label: str, job: JobContext) -> DocumentSnapshot:
        """Rebuild, persist as the new head revision and notify the renderer.

        The rebuild runs before anything is written, so a cancelled or failing
        rebuild leaves the session unchanged.
        """
        revision = self.revisions.peek_next()
        document = replace(document, revision=revision)
        built = self._build(document, label, job)
        previous_scan = self._document.scan
        mesh_changing = document.scan is not None and (
            previous_scan is None or previous_scan.key != document.scan.key
        )
        dropped = self.revisions.append(self._persisted(document), label, mesh_changing)
        dropped += self.revisions.prune()
        if dropped or mesh_changing:
            self._collect_blobs()
        self._document, self._label, self._built = document, label, built
        return self._publish("commit", job)

    def checkout(self, revision: int, job: JobContext) -> DocumentSnapshot:
        """Make an earlier or later revision the head (undo and redo)."""
        stored = self.revisions.read(revision)
        document = self._restore(stored.document)
        built = self._build(document, stored.label, job)
        self.revisions.set_head(revision)
        self._document, self._label, self._built = document, stored.label, built
        return self._publish("checkout", job)

    def close(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def _publish(self, cause: ChangeCause, job: JobContext) -> DocumentSnapshot:
        snapshot = self.snapshot(cause, job)
        self._events.emit_event("documentChanged", to_json(snapshot, DocumentSnapshot))
        return snapshot

    def _build(self, document: Document, label: str, job: JobContext) -> BuiltDocument:
        result = rebuild(document, self.environment(), job)
        sources: dict[str, tuple[str, tuple[DisplaySource, ...]]] = {
            feature_id: (result.result_keys[feature_id], output.display)
            for feature_id, output in result.outputs.items()
            if output.display
        }
        scene = build_scene(
            document,
            result.matrix,
            dict(result.bodies),
            dict(result.body_keys),
            dict(result.body_owner),
            sources,
            self.blobs,
            self.scene,
        )
        bodies = tuple(
            BodyInfo(
                id=body_id,
                owner=result.body_owner[body_id],
                valid=check.valid,
                solids=check.solids,
                volume=check.volume,
                area=check.area,
                max_tolerance=check.max_tolerance,
                face_tags=result.bodies[body_id].face_tags,
            )
            for body_id, check in result.body_checks.items()
        )
        status = DocumentStatus(features=dict(result.statuses), bodies=bodies)
        return BuiltDocument(document, label, result, status, scene)

    def _load_head(self) -> tuple[Document, str]:
        head = self.revisions.head
        if head is None:
            document = Document.empty()
            self.revisions.append(self._persisted(document), "new", mesh_changing=False)
            return document, "new"
        stored = self.revisions.read(head)
        return self._restore(stored.document), stored.label

    @staticmethod
    def _persisted(document: Document) -> dict[str, Any]:
        return {
            "format": DOCUMENT_FORMAT,
            "version": DOCUMENT_VERSION,
            "document": to_json(document, Document),
        }

    @staticmethod
    def _restore(data: Mapping[str, Any]) -> Document:
        return from_json(data["document"], Document)

    def _collect_blobs(self) -> None:
        referenced: set[str] = set()
        for data in self.revisions.documents():
            referenced |= self._restore(data).blob_refs()
        removed = self.blobs.collect(referenced)
        if removed:
            log.info("removed %d unreferenced blobs", removed)
