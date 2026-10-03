"""Synthetic scans in random poses, stored as documents of a test session."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest

from m2c_kernel.document.model import (
    Alignment,
    Document,
    Feature,
    Region,
    RegionKind,
    Regions,
    Scan,
    ScanSource,
)
from m2c_kernel.fitting.primitives import Plane
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.session.session import Session
from tests.synthetic import add_scanner_noise, random_pose
from tests.synthetic.parts import SyntheticPart, block_part

SIGMA = 0.03
BLOCK_EDGE_MM = 2.0
"""Coarser than the default block: plenty of triangles per face, faster tests."""


@dataclass(frozen=True)
class PosedScan:
    document: Document
    part: SyntheticPart
    rotation: np.ndarray
    """Design -> scan rotation."""
    offset: np.ndarray
    """Design origin in scan coordinates."""

    def design_to_scan(self, points: np.ndarray) -> np.ndarray:
        result: np.ndarray = np.asarray(points) @ self.rotation.T + self.offset
        return result


def pose_scan(session: Session, part: SyntheticPart, seed: int, sigma: float = SIGMA) -> PosedScan:
    """The part with scanner noise (0.1 % spikes) in a random pose, as a document."""
    rng = np.random.default_rng(seed)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, sigma, rng, spike_fraction=0.001)
    vertices, _, rotation, offset = random_pose(noisy, normals, rng)
    origin = np.round(vertices.mean(axis=0), 1)
    blobs = session.blobs
    vertex_ref = blobs.put((vertices - origin).astype(np.float32))
    face_ref = blobs.put(part.faces.astype(np.uint32))
    scan = Scan(
        key=f"scan:{vertex_ref[5:17]}{face_ref[5:13]}",
        source=ScanSource("part.stl", "0", "mm"),
        vertices=vertex_ref,
        faces=face_ref,
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(part.faces),
        origin=(float(origin[0]), float(origin[1]), float(origin[2])),
        noise=sigma,
    )
    document = replace(Document.empty(), scan=scan)
    return PosedScan(document, part, rotation, offset)


def plane_face(part: SyntheticPart, normal: tuple[float, float, float], offset: float) -> int:
    """Index of the B-Rep plane with the given outward design normal and offset."""
    for index, surface in enumerate(part.surfaces):
        if not isinstance(surface, Plane):
            continue
        n = np.asarray(surface.normal)
        if (
            abs(float(n @ normal) - 1.0) < 1e-6
            and abs(float(np.asarray(surface.origin) @ n) - offset) < 1e-6
        ):
            return index
    raise LookupError((normal, offset))


def surface_face(part: SyntheticPart, kind: str, largest: bool = True) -> int:
    """Index of the largest (by triangle count) B-Rep face of a type."""
    candidates = [
        index
        for index, surface in enumerate(part.surfaces)
        if surface is not None and surface.type == kind
    ]
    counts = [int((part.labels == index).sum()) for index in candidates]
    return candidates[int(np.argmax(counts) if largest else np.argmin(counts))]


def with_fit(
    session: Session, posed: PosedScan, feature_id: str, kind: str, brep_face: int
) -> PosedScan:
    faces = np.nonzero(posed.part.labels == brep_face)[0].astype(np.uint32)
    params: dict[str, JsonValue] = {
        "faces": session.blobs.put(faces),
        "sourceRegion": None,
        "kind": kind,
        "robust": False,
        "fixed": {},
        "relation": None,
        "snap": True,
        "rejectedSnaps": [],
    }
    feature = Feature(id=feature_id, type="fit", name=None, suppressed=False, params=params)
    document = replace(posed.document, features=(*posed.document.features, feature))
    return replace(posed, document=document)


def with_regions(
    session: Session, posed: PosedScan, regions: dict[str, tuple[RegionKind, int]]
) -> PosedScan:
    """Regions by id: (kind, B-Rep face index)."""
    labels = np.zeros(len(posed.part.faces), dtype=np.uint16)
    items = []
    for label, (region_id, (kind, brep_face)) in enumerate(regions.items(), start=1):
        mask = posed.part.labels == brep_face
        labels[mask] = label
        items.append(Region(region_id, label, None, kind, None, int(mask.sum()), 0.0, label))
    region_state = Regions(labels=session.blobs.put(labels), items=tuple(items))
    return replace(posed, document=replace(posed.document, regions=region_state))


def with_alignment(posed: PosedScan, alignment: Alignment) -> PosedScan:
    return replace(posed, document=replace(posed.document, alignment=alignment))


@pytest.fixture(scope="session")
def block() -> SyntheticPart:
    return block_part(BLOCK_EDGE_MM)
