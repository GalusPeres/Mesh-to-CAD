"""Fixtures of the surfacing tests: an in-process decimator and scan documents."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.document.model import Document, DocumentSettings, Feature, Scan, ScanSource
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.session import Session
from m2c_kernel.surfacing.cage import Decimator
from tests.surfacing.shapes import FloatArray, IntArray

AGGRESSIVENESS = 5.0
"""As `m2c_kernel.mesh.decimate.AGGRESSIVENESS`."""


def simplify(vertices: FloatArray, faces: IntArray, target: int) -> tuple[FloatArray, IntArray]:
    """fast_simplification in this process (the kernel runs it in a child process)."""
    import fast_simplification

    out_vertices, out_faces = fast_simplification.simplify(
        vertices.astype(np.float32), faces.astype(np.int32), target_count=target, agg=AGGRESSIVENESS
    )
    return np.asarray(out_vertices, np.float64), np.asarray(out_faces, np.int64)


@pytest.fixture
def decimator() -> Decimator:
    return simplify


@pytest.fixture
def in_process_decimation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Features decimate in this process, which keeps the rebuild tests fast."""
    monkeypatch.setattr("m2c_kernel.surfacing.api._child_process_decimator", lambda job: simplify)


def scan_document(
    session: Session, vertices: FloatArray, faces: IntArray, noise: float
) -> Document:
    """A document whose scan is the given mesh (identity alignment)."""
    vertex_ref = session.blobs.put(vertices.astype(np.float32))
    face_ref = session.blobs.put(faces.astype(np.uint32))
    scan = Scan(
        key=f"scan:{vertex_ref[5:17]}{face_ref[5:13]}",
        source=ScanSource("organic.stl", "0", "mm"),
        vertices=vertex_ref,
        faces=face_ref,
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=(0.0, 0.0, 0.0),
        noise=noise,
    )
    settings = DocumentSettings(tolerance=0.1, noise_override=noise)
    return replace(Document.empty(), scan=scan, settings=settings)


def with_feature(
    document: Document, feature_id: str, type_id: str, params: dict[str, JsonValue]
) -> Document:
    feature = Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=params)
    return replace(document, features=(*document.features, feature))
