"""Linear revision history of the document, persisted in the session directory.

Layout: `revisions/<n>.json` (one document snapshot each) and `head.json`
(`{"head": n, "next": m}`). The head is persisted so that a kernel restarted
after a crash continues at the revision the user had checked out, not at the
newest one. Revision numbers are never reused, so an undo entry in the renderer
can never point at a different document than the one it was made for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2c_kernel.codes.document import ErrorCode
from m2c_kernel.limits import MAX_MESH_REVISIONS, MAX_REVISIONS
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.fs import atomic_write_bytes, remove_quietly


@dataclass(frozen=True)
class StoredRevision:
    revision: int
    label: str
    mesh_changing: bool
    document: dict[str, Any]


class RevisionStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._revisions = directory / "revisions"
        self._revisions.mkdir(parents=True, exist_ok=True)
        self._head_file = directory / "head.json"
        self.head: int | None = None
        self._next = 0
        self._mesh_changing: dict[int, bool] = {}
        if self._head_file.exists():
            state = json.loads(self._head_file.read_text(encoding="utf-8"))
            self.head, self._next = int(state["head"]), int(state["next"])

    def peek_next(self) -> int:
        """The number the next appended revision will get."""
        return self._next

    def numbers(self) -> list[int]:
        return sorted(int(path.stem) for path in self._revisions.glob("*.json"))

    def read(self, revision: int) -> StoredRevision:
        path = self._path(revision)
        if not path.exists():
            raise KernelError(ErrorCode.REVISION_GONE, {"revision": revision})
        data = json.loads(path.read_text(encoding="utf-8"))
        self._mesh_changing[revision] = bool(data["meshChanging"])
        return StoredRevision(revision, data["label"], data["meshChanging"], data["document"])

    def is_mesh_changing(self, revision: int) -> bool:
        if revision not in self._mesh_changing:
            self.read(revision)
        return self._mesh_changing[revision]

    def append(self, document: dict[str, Any], label: str, mesh_changing: bool) -> list[int]:
        """Store a new revision after the head, dropping the revisions that followed it.

        Returns the numbers of the dropped revisions (the redo part of the history).
        """
        dropped = []
        if self.head is not None:
            for number in self.numbers():
                if number > self.head:
                    remove_quietly(self._path(number))
                    self._mesh_changing.pop(number, None)
                    dropped.append(number)
        revision = self._next
        payload = {"label": label, "meshChanging": mesh_changing, "document": document}
        atomic_write_bytes(self._path(revision), json.dumps(payload).encode("utf-8"))
        self._mesh_changing[revision] = mesh_changing
        self._next = revision + 1
        self.set_head(revision)
        return dropped

    def set_head(self, revision: int) -> None:
        if not self._path(revision).exists():
            raise KernelError(ErrorCode.REVISION_GONE, {"revision": revision})
        self.head = revision
        state = json.dumps({"head": revision, "next": self._next}).encode("utf-8")
        atomic_write_bytes(self._head_file, state)

    def prune(self) -> list[int]:
        """Drop the oldest revisions beyond the limits; returns the dropped numbers.

        Two limits apply: at most `MAX_REVISIONS` revisions, and at most
        `MAX_MESH_REVISIONS` revisions that introduced a new scan (each of those
        can reference tens of megabytes of blobs). The head is never dropped.
        """
        numbers = self.numbers()
        mesh_changing = [n for n in numbers if self.is_mesh_changing(n)]
        dropped: list[int] = []
        while numbers and numbers[0] != self.head:
            too_many = len(numbers) > MAX_REVISIONS
            too_many_meshes = len(mesh_changing) > MAX_MESH_REVISIONS
            if not (too_many or too_many_meshes):
                break
            oldest = numbers.pop(0)
            if mesh_changing and mesh_changing[0] == oldest:
                mesh_changing.pop(0)
            remove_quietly(self._path(oldest))
            self._mesh_changing.pop(oldest, None)
            dropped.append(oldest)
        return dropped

    def documents(self) -> list[dict[str, Any]]:
        """Every kept document snapshot (for blob garbage collection)."""
        return [self.read(number).document for number in self.numbers()]

    def _path(self, revision: int) -> Path:
        return self._revisions / f"{revision}.json"
