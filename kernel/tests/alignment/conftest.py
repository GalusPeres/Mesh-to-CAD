"""Scans of the synthetic block in random poses, stored as documents for the alignment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.document.model import Document, Feature, Region, Regions, Scan, ScanSource
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.session.blobs import BlobStore
from tests.synthetic import add_scanner_noise, random_pose
from tests.synthetic.parts import SyntheticPart, block_part

SIGMA = 0.03


@dataclass(frozen=True)
class PosedScan:
    document: Document
    blobs: BlobStore
    rotation: np.ndarray
    """Design -> scan rotation."""
    offset: np.ndarray
    part: SyntheticPart


def pose_scan(part: SyntheticPart, seed: int, blobs: BlobStore, sigma: float = SIGMA) -> PosedScan:
    rng = np.random.default_rng(seed)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, sigma, rng, spike_fraction=0.001)
    vertices, _, rotation, offset = random_pose(noisy, normals, rng)
    scan = Scan(
        key=f"scan:test{seed}",
        source=ScanSource("block.stl", "0", "mm"),
        vertices=blobs.put(vertices.astype(np.float32)),
        faces=blobs.put(part.faces.astype(np.uint32)),
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(part.faces),
        origin=(0.0, 0.0, 0.0),
        noise=sigma,
    )
    document = replace(Document.empty(), scan=scan)
    return PosedScan(document, blobs, rotation, offset, part)


def brep_face(part: SyntheticPart, kind: str, normal: tuple[float, float, float], offset: float) -> int:
    """Index of the analytic B-Rep face of `kind` with the given design normal and offset."""
    for index, surface in enumerate(part.surfaces):
        if surface is None or surface.type != kind:
            continue
        if kind == "plane":
            n = np.asarray(surface.normal)  # type: ignore[union-attr]
            if abs(abs(n @ normal) - 1) < 1e-6 and abs(np.asarray(surface.origin) @ normal - offset) < 1e-6:  # type: ignore[union-attr]
                return index
    raise LookupError((kind, normal, offset))


def with_fit(posed: PosedScan, feature_id: str, kind: str, face_label: int) -> PosedScan:
    faces = np.nonzero(posed.part.labels == face_label)[0].astype(np.uint32)
    params = {"faces": posed.blobs.put(faces), "kind": kind, "sourceRegion": None}
    feature = Feature(id=feature_id, type="fit", name=None, suppressed=False, params=params)
    document = replace(posed.document, features=(*posed.document.features, feature))
    return replace(posed, document=document)


def with_region(posed: PosedScan, region_id: str, kind: str, face_label: int) -> PosedScan:
    labels = (posed.part.labels == face_label).astype(np.uint16)
    region = Region(region_id, 1, None, kind, None, int(labels.sum()), 0.0, 0)  # type: ignore[arg-type]
    regions = Regions(labels=posed.blobs.put(labels), items=(region,))
    return replace(posed, document=replace(posed.document, regions=regions))


@pytest.fixture(scope="module")
def blobs(tmp_path_factory: pytest.TempPathFactory) -> BlobStore:
    return BlobStore(Path(tmp_path_factory.mktemp("blobs")))


@pytest.fixture(scope="module")
def block() -> SyntheticPart:
    return block_part(1.0)
