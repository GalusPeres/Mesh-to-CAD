"""The synthetic block with scanner noise, as an evaluation mesh and as a session document."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt
import pytest

from m2c_kernel.document.model import Document, Scan, ScanSource
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.primitives import Cylinder, Plane
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic import add_scanner_noise
from tests.synthetic.parts import SyntheticPart, block_part

SIGMA = 0.03
SMALL_EDGE_MM = 2.0
"""331 k faces: reduced to the 200 k working copy like a real scan, still quick to build."""


@dataclass(frozen=True)
class NoisyPart:
    part: SyntheticPart
    mesh: EvalMesh

    def truth(self, brep_face: int) -> npt.NDArray[np.bool_]:
        result: npt.NDArray[np.bool_] = self.part.labels == brep_face
        return result

    def iou(self, faces: npt.NDArray[np.int64] | npt.NDArray[np.bool_], brep_face: int) -> float:
        """Intersection over union by area against a true B-Rep face."""
        mask = np.zeros(len(self.mesh.faces), dtype=bool)
        mask[faces] = True
        truth = self.truth(brep_face)
        area = self.mesh.face_areas
        return float(area[mask & truth].sum() / area[mask | truth].sum())

    def interior_face(self, brep_face: int) -> int:
        """The face of a B-Rep face farthest (in rings) from every other B-Rep face."""
        neighbours = self.mesh.face_graph.neighbours
        labels = self.part.labels
        other = np.where(neighbours >= 0, labels[np.maximum(neighbours, 0)], -1)
        frontier = np.nonzero(((other != labels[:, None]) & (other >= 0)).any(axis=1))[0]
        distance = np.full(len(labels), -1)
        distance[frontier] = 0
        ring = 0
        while len(frontier):
            ring += 1
            reached = neighbours[frontier].ravel()
            reached = np.unique(reached[reached >= 0])
            frontier = reached[distance[reached] < 0]
            distance[frontier] = ring
        members = np.nonzero(labels == brep_face)[0]
        return int(members[np.argmax(distance[members])])

    def plane_face(self, normal: tuple[float, float, float], offset: float) -> int:
        """The B-Rep plane with this outward normal and distance from the origin."""
        for index, surface in enumerate(self.part.surfaces):
            if isinstance(surface, Plane):
                n = np.asarray(surface.normal)
                if (
                    n @ normal > 0.999
                    and abs(float(np.asarray(surface.origin) @ n) - offset) < 1e-6
                ):
                    return index
        raise LookupError((normal, offset))

    def cylinder_faces(self, radius: float) -> list[int]:
        """The B-Rep cylinders with this radius."""
        return [
            index
            for index, surface in enumerate(self.part.surfaces)
            if isinstance(surface, Cylinder) and abs(surface.radius - radius) < 1e-6
        ]

    def face_of(self, kind: str, *, largest: bool = True) -> int:
        """The largest (or smallest) B-Rep face of a type, by area."""
        area = self.mesh.face_areas
        candidates = [
            index
            for index, surface in enumerate(self.part.surfaces)
            if surface is not None and surface.type == kind
        ]
        sizes = [float(area[self.part.labels == index].sum()) for index in candidates]
        return candidates[int(np.argmax(sizes) if largest else np.argmin(sizes))]


def noisy_block(edge: float, seed: int = 7) -> NoisyPart:
    """The test block with 0.03 mm noise and 0.1 % spikes, in design coordinates."""
    part = block_part(edge)
    rng = np.random.default_rng(seed)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, SIGMA, rng, spike_fraction=0.001)
    return NoisyPart(part, EvalMesh(f"mesh:block{edge}:{seed}", noisy, part.faces, None))


@pytest.fixture(scope="session")
def small_block() -> NoisyPart:
    return noisy_block(SMALL_EDGE_MM)


def open_block_document(session: Session, block: NoisyPart, job: JobContext) -> Scan:
    """Commit the noisy block as the session's scan (identity alignment)."""
    blobs = session.blobs
    vertices = block.mesh.vertices
    origin = np.round(vertices.mean(axis=0), 1)
    vertex_ref = blobs.put((vertices - origin).astype(np.float32))
    face_ref = blobs.put(block.mesh.faces.astype(np.uint32))
    scan = Scan(
        key=f"scan:{vertex_ref[5:17]}{face_ref[5:13]}",
        source=ScanSource("block.stl", "0", "mm"),
        vertices=vertex_ref,
        faces=face_ref,
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(block.mesh.faces),
        origin=(float(origin[0]), float(origin[1]), float(origin[2])),
        noise=SIGMA,
    )
    session.commit(replace(Document.empty(), scan=scan), "import", job)
    return scan
