"""The document state sent to the renderer after every change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from m2c_kernel.document.display import SceneManifest
from m2c_kernel.document.model import Document
from m2c_kernel.document.results import BodyInfo, FeatureStatus

type ChangeCause = Literal["commit", "checkout", "restore", "current"]


@dataclass(frozen=True)
class DocumentStatus:
    features: dict[str, FeatureStatus]
    bodies: tuple[BodyInfo, ...]


@dataclass(frozen=True)
class DocumentSnapshot:
    """Payload of the `documentChanged` event and result of `doc.get`.

    `cause` tells the renderer how to treat its undo history: `commit` adds an
    entry, `checkout` moves within it, `restore` (kernel restart, project load)
    and `current` (explicit `doc.get`) reset it.
    """

    revision: int
    cause: ChangeCause
    label: str
    document: Document
    status: DocumentStatus
    scene: SceneManifest
