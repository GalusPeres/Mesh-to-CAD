"""The `.m2c` project file: a ZIP with manifest, document, view state and blobs.

Layout and rules: ARCHITECTURE.md 4.10. The document is the source of truth;
bodies are never stored and are rebuilt after loading. Blobs are stored as they
are in the session (scan vertices are float32 relative to `scan.origin`), each
under its content hash, which is verified when the file is read.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from m2c_kernel import __version__
from m2c_kernel.codes.project import ErrorCode
from m2c_kernel.document.model import DOCUMENT_FORMAT, DOCUMENT_VERSION, Document
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue, from_json, to_json
from m2c_kernel.session.blobs import BlobStore, blob_digest
from m2c_kernel.session.fs import replace_with_retry

PROJECT_FORMAT = "mesh-to-cad-project"
PROJECT_VERSION = 1

_FIXED_ENTRIES = frozenset({"manifest.json", "document.json", "ui.json", "thumbnail.png"})
_BLOB_ENTRY = re.compile(r"blobs/([0-9a-f]{64})\.npy")

type Migration = Callable[[dict[str, Any]], dict[str, Any]]

MIGRATIONS: dict[int, Migration] = {}
"""`MIGRATIONS[n]` turns the document JSON of file version n into version n + 1."""


@dataclass(frozen=True)
class LoadedProject:
    document: Document
    ui_state: JsonValue


def save_project(path: Path, document: Document, ui_state: JsonValue, blobs: BlobStore) -> None:
    """Write atomically next to the target and keep the previous file as `.m2c.bak`."""
    refs = sorted(document.blob_refs())
    arrays = {ref.removeprefix("blob:"): blobs.get(ref) for ref in refs}
    manifest = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "app": __version__,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "blobs": {
            digest: {"dtype": array.dtype.str, "shape": list(array.shape)}
            for digest, array in arrays.items()
        },
    }
    stored_document = {
        "format": DOCUMENT_FORMAT,
        "version": DOCUMENT_VERSION,
        "document": to_json(document, Document),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("document.json", json.dumps(stored_document))
            archive.writestr("ui.json", json.dumps(ui_state))
            for digest, array in arrays.items():
                buffer = io.BytesIO()
                np.save(buffer, array, allow_pickle=False)
                archive.writestr(f"blobs/{digest}.npy", buffer.getvalue())
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copy2(path, path.with_name(f"{path.name}.bak"))
        replace_with_retry(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def load_project(path: Path, blobs: BlobStore) -> LoadedProject:
    """Read the manifest first; reject unknown formats and newer versions."""
    try:
        with zipfile.ZipFile(path) as archive:
            return _read(archive, blobs)
    except KernelError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, TypeError) as error:
        raise KernelError(ErrorCode.CORRUPT, details=repr(error)) from error


def _read(archive: zipfile.ZipFile, blobs: BlobStore) -> LoadedProject:
    names = archive.namelist()
    for name in names:
        if name not in _FIXED_ENTRIES and _BLOB_ENTRY.fullmatch(name) is None:
            raise KernelError(ErrorCode.CORRUPT, details=f"unexpected entry {name!r}")
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != PROJECT_FORMAT:
        raise KernelError(ErrorCode.CORRUPT, details="not a Mesh-to-CAD project")
    version = manifest.get("version")
    if not isinstance(version, int) or version < 1:
        raise KernelError(ErrorCode.CORRUPT, details=f"invalid version {version!r}")
    if version > PROJECT_VERSION:
        raise KernelError(
            ErrorCode.UNSUPPORTED_VERSION, {"version": version, "supported": PROJECT_VERSION}
        )

    stored = json.loads(archive.read("document.json"))
    data: dict[str, Any] = stored["document"]
    for step in range(version, PROJECT_VERSION):
        data = MIGRATIONS[step](data)
    document = from_json(data, Document)
    ui_state: JsonValue = json.loads(archive.read("ui.json")) if "ui.json" in names else None

    for name in names:
        match = _BLOB_ENTRY.fullmatch(name)
        if match is None:
            continue
        array = np.load(io.BytesIO(archive.read(name)), allow_pickle=False)
        if blob_digest(array) != match.group(1):
            raise KernelError(ErrorCode.CORRUPT, details=f"blob {name} does not match its hash")
        blobs.put(array)
    missing = [ref for ref in document.blob_refs() if not blobs.contains(ref)]
    if missing:
        raise KernelError(ErrorCode.CORRUPT, details=f"{len(missing)} blobs missing")
    return LoadedProject(document, ui_state)
