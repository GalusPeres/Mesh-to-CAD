"""Freeform test documents: synthetic scans stored in a test session."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from m2c_kernel.document.model import Document, DocumentSettings, Feature, Scan, ScanSource
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.session import Session
from tests.freeform.shapes import FloatArray, IntArray


def scan_document(
    session: Session, vertices: FloatArray, faces: IntArray, noise: float, tolerance: float = 0.1
) -> Document:
    """A document whose scan is the given mesh (identity alignment)."""
    origin = np.round(vertices.mean(axis=0), 1)
    vertex_ref = session.blobs.put((vertices - origin).astype(np.float32))
    face_ref = session.blobs.put(faces.astype(np.uint32))
    scan = Scan(
        key=f"scan:{vertex_ref[5:17]}{face_ref[5:13]}",
        source=ScanSource("freeform.stl", "0", "mm"),
        vertices=vertex_ref,
        faces=face_ref,
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=(float(origin[0]), float(origin[1]), float(origin[2])),
        noise=noise,
    )
    settings = DocumentSettings(tolerance=tolerance, noise_override=noise)
    return replace(Document.empty(), scan=scan, settings=settings)


def with_feature(
    document: Document, feature_id: str, type_id: str, params: dict[str, JsonValue]
) -> Document:
    feature = Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=params)
    return replace(document, features=(*document.features, feature))
