"""The `.m2c` project file: a ZIP with manifest, document, view state and blobs.

Layout and rules: ARCHITECTURE.md 4.10. The document is the source of truth;
bodies are never stored and are rebuilt after loading. Blobs are stored as they
are in the session (scan vertices are float32 relative to `scan.origin`), each
under its content hash, which is verified when the file is read.

A project file comes from outside the application, so reading trusts nothing:
entries other than the known names and `blobs/<sha256>.npy` are rejected (no
path of an entry is ever used to write a file), sizes are checked against the
manifest before anything is decompressed, and every blob must match its hash.
"""

from __future__ import annotations

import contextlib
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
"""Version of the file layout and of the stored document; raised with every migration."""

MANIFEST, DOCUMENT, UI_STATE, THUMBNAIL = (
    "manifest.json",
    "document.json",
    "ui.json",
    "thumbnail.png",
)
_BLOB_ENTRY = re.compile(r"blobs/([0-9a-f]{64})\.npy")
_BLOB_DTYPES = frozenset({"|b1", "|u1", "<u2", "<u4", "<i4", "<i8", "<f4", "<f8"})
_NPY_HEADER_BYTES = 4096
_MAX_JSON_BYTES = {MANIFEST: 64 << 20, DOCUMENT: 256 << 20, UI_STATE: 16 << 20, THUMBNAIL: 16 << 20}
_MAX_TOTAL_BYTES = 8 << 30
_COMPRESS_LEVEL = 1
"""Scan coordinates barely compress; a low level keeps saving fast for large scans."""

type Migration = Callable[[dict[str, Any]], dict[str, Any]]

MIGRATIONS: dict[int, Migration] = {}
"""`MIGRATIONS[n]` turns the document JSON of file version n into version n + 1.

Each migration comes with a stored fixture of version n (`kernel/tests/project/fixtures`)
that must keep loading.
"""


@dataclass(frozen=True)
class LoadedProject:
    document: Document
    ui_state: JsonValue


def save_project(path: Path, document: Document, ui_state: JsonValue, blobs: BlobStore) -> None:
    """Write the project next to the target, then replace the target in one step.

    The previous file is kept as `<name>.bak`. Any failure before the final
    replace leaves the existing file untouched.
    """
    refs = sorted(document.blob_refs())
    shapes: dict[str, dict[str, Any]] = {}
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=_COMPRESS_LEVEL
        ) as archive:
            for ref in refs:
                array = blobs.get(ref)
                digest = ref.removeprefix("blob:")
                shapes[digest] = {"dtype": array.dtype.str, "shape": list(array.shape)}
                with archive.open(f"blobs/{digest}.npy", "w", force_zip64=True) as entry:
                    np.save(entry, array, allow_pickle=False)
            stored = {
                "format": DOCUMENT_FORMAT,
                "version": DOCUMENT_VERSION,
                "document": to_json(document, Document),
            }
            archive.writestr(DOCUMENT, json.dumps(stored))
            archive.writestr(UI_STATE, json.dumps(ui_state))
            manifest = {
                "format": PROJECT_FORMAT,
                "version": PROJECT_VERSION,
                "app": __version__,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
                "blobs": shapes,
            }
            archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copyfile(path, path.with_name(f"{path.name}.bak"))
        replace_with_retry(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def load_project(path: Path, blobs: BlobStore) -> LoadedProject:
    """Read and verify a project; its blobs are added to `blobs`.

    Fails with `project.corrupt` for anything that is not a complete, consistent
    project file, with `project.unsupportedVersion` for files of a newer version and
    with `project.readFailed` when the file cannot be read at all.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return _read(archive, blobs)
    except KernelError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, ValueError, KeyError) as error:
        raise KernelError(ErrorCode.CORRUPT, details=repr(error)) from error
    except OSError as error:
        raise KernelError(ErrorCode.READ_FAILED, details=repr(error)) from error


def _read(archive: zipfile.ZipFile, blobs: BlobStore) -> LoadedProject:
    entries = _checked_entries(archive)
    manifest = _json(archive, entries, MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("format") != PROJECT_FORMAT:
        raise _corrupt("not a Mesh-to-CAD project")
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise _corrupt(f"invalid version {version!r}")
    if version > PROJECT_VERSION:
        raise KernelError(
            ErrorCode.UNSUPPORTED_VERSION, {"version": version, "supported": PROJECT_VERSION}
        )
    declared = _declared_blobs(manifest, entries)

    stored = _json(archive, entries, DOCUMENT)
    if not isinstance(stored, dict) or stored.get("format") != DOCUMENT_FORMAT:
        raise _corrupt("document.json is not a Mesh-to-CAD document")
    data = stored.get("document")
    if not isinstance(data, dict):
        raise _corrupt("document.json has no document")
    for step in range(version, PROJECT_VERSION):
        data = MIGRATIONS[step](data)
    try:
        document = from_json(data, Document)
    except (KernelError, TypeError, ValueError) as error:
        raise _corrupt(f"invalid document: {error}") from error
    ui_state: JsonValue = _json(archive, entries, UI_STATE) if UI_STATE in entries else None

    missing = [ref for ref in document.blob_refs() if ref.removeprefix("blob:") not in declared]
    if missing:
        raise _corrupt(f"{len(missing)} referenced blobs are not in the file")
    for digest, (dtype, shape) in declared.items():
        with archive.open(entries[f"blobs/{digest}.npy"]) as entry:
            array = np.load(entry, allow_pickle=False)
        if array.dtype.str != dtype or list(array.shape) != shape or blob_digest(array) != digest:
            raise _corrupt(f"blob {digest} does not match the manifest or its hash")
        blobs.put(array)
    return LoadedProject(document, ui_state)


def _checked_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    """The entries by name; any other name, a duplicate or an oversized file is rejected."""
    entries: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in archive.infolist():
        name = info.filename
        if name in entries:
            raise _corrupt(f"duplicate entry {name!r}")
        if name not in _MAX_JSON_BYTES and _BLOB_ENTRY.fullmatch(name) is None:
            raise _corrupt(f"unexpected entry {name!r}")
        if name in _MAX_JSON_BYTES and info.file_size > _MAX_JSON_BYTES[name]:
            raise _corrupt(f"{name} is too large")
        total += info.file_size
        entries[name] = info
    if total > _MAX_TOTAL_BYTES:
        raise _corrupt("the file unpacks to more than the size limit")
    for required in (MANIFEST, DOCUMENT):
        if required not in entries:
            raise _corrupt(f"{required} is missing")
    return entries


def _declared_blobs(
    manifest: dict[str, Any], entries: dict[str, zipfile.ZipInfo]
) -> dict[str, tuple[str, list[int]]]:
    """Blobs of the manifest, checked against the entries and their unpacked size."""
    listed = manifest.get("blobs")
    if not isinstance(listed, dict):
        raise _corrupt("the manifest lists no blobs")
    stored = {
        match.group(1) for name in entries if (match := _BLOB_ENTRY.fullmatch(name)) is not None
    }
    if stored != set(listed):
        raise _corrupt("the blobs in the file differ from the manifest")
    declared: dict[str, tuple[str, list[int]]] = {}
    for digest, info in listed.items():
        dtype = info.get("dtype") if isinstance(info, dict) else None
        shape = info.get("shape") if isinstance(info, dict) else None
        valid_shape = isinstance(shape, list) and all(
            isinstance(size, int) and not isinstance(size, bool) and size >= 0 for size in shape
        )
        if dtype not in _BLOB_DTYPES or not valid_shape:
            raise _corrupt(f"blob {digest} has an invalid type")
        assert isinstance(dtype, str) and isinstance(shape, list)
        expected = int(np.prod(shape, dtype=np.int64)) * np.dtype(dtype).itemsize
        if entries[f"blobs/{digest}.npy"].file_size > expected + _NPY_HEADER_BYTES:
            raise _corrupt(f"blob {digest} is larger than its manifest entry")
        declared[digest] = (dtype, shape)
    return declared


def _json(archive: zipfile.ZipFile, entries: dict[str, zipfile.ZipInfo], name: str) -> Any:
    try:
        return json.loads(archive.read(entries[name]))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _corrupt(f"{name} is not valid JSON") from error


def _corrupt(details: str) -> KernelError:
    return KernelError(ErrorCode.CORRUPT, details=details)
