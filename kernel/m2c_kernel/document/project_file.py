"""The `.m2c` project file: a ZIP with manifest, document, view state and blobs.

Not implemented yet. Layout and rules: ARCHITECTURE.md 4.10.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from m2c_kernel.document.model import Document
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.blobs import BlobStore

PROJECT_FORMAT = "mesh-to-cad-project"
PROJECT_VERSION = 1


@dataclass(frozen=True)
class LoadedProject:
    document: Document
    ui_state: JsonValue


def save_project(path: Path, document: Document, ui_state: JsonValue, blobs: BlobStore) -> None:
    """Write atomically next to the target and keep the previous file as `.m2c.bak`."""
    raise NotImplementedError("saving projects")


def load_project(path: Path, blobs: BlobStore) -> LoadedProject:
    """Read the manifest first; reject unknown formats and newer versions."""
    raise NotImplementedError("loading projects")
