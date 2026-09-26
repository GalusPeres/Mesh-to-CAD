"""A noisy closed scan with known, countable defects."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.load import RawMesh
from m2c_kernel.session.jobs import seeded_rng
from tests.synthetic import add_scanner_noise, box_scan, sphere_scan

type IntArray = npt.NDArray[np.int64]

HOLE_CENTRES = ((20.0, 20.0), (50.0, 35.0), (80.0, 50.0))
HOLE_RADIUS = 2.5
FLIP_CENTRE = (60.0, 0.0, 10.0)
FLIP_RADIUS = 6.0
DEBRIS_PARTS = 12
DUPLICATES = 40
DEGENERATES = 25


@dataclass(frozen=True)
class DirtyScan:
    """The dirty mesh and what was injected into it.

    `clean_faces` indexes the faces of the part itself (without holes, debris and
    injected faces); `debris_faces` the loose parts; `flipped` the faces of the
    part whose winding was reversed.
    """

    mesh: RawMesh
    clean_faces: IntArray
    debris_faces: IntArray
    flipped: IntArray
    holes: int


def dirty_box_scan(sigma: float = 0.03) -> DirtyScan:
    """Box 100 x 70 x 20 mm with scanner noise, three holes in the top, a flipped patch
    on the front, loose debris, duplicate and degenerate faces."""
    rng = seeded_rng("dirty-box-scan")
    vertices, faces = box_scan(max_edge=1.5)
    normals = _vertex_normals_of_box(vertices)
    vertices = add_scanner_noise(vertices, normals, sigma, rng, spike_fraction=0.001)

    centroids = vertices[faces].mean(axis=1)
    on_top = np.abs(centroids[:, 2] - 20.0) < 0.2
    in_hole = np.zeros(len(faces), dtype=bool)
    for x, y in HOLE_CENTRES:
        in_hole |= on_top & (np.hypot(centroids[:, 0] - x, centroids[:, 1] - y) < HOLE_RADIUS)
    faces = faces[~in_hole]
    centroids = centroids[~in_hole]

    near_patch = np.linalg.norm(centroids - np.asarray(FLIP_CENTRE), axis=1) < FLIP_RADIUS
    flipped = np.flatnonzero(near_patch & (np.abs(centroids[:, 1]) < 0.2))
    faces = faces.copy()
    faces[flipped] = faces[flipped, ::-1]
    part_faces = len(faces)

    debris_vertices = [vertices]
    debris_faces = []
    offset = len(vertices)
    small_vertices, small_faces = sphere_scan(radius=0.6, subdivisions=1)
    for index in range(DEBRIS_PARTS):
        position = np.array([10.0 + 7.0 * index, -8.0, 5.0 + (index % 3)])
        debris_vertices.append(small_vertices + position)
        debris_faces.append(small_faces + offset)
        offset += len(small_vertices)
    all_vertices = np.vstack(debris_vertices)
    debris = np.vstack(debris_faces)

    candidates = np.setdiff1d(np.arange(part_faces), flipped)
    duplicate_sources = rng.choice(candidates, DUPLICATES, replace=False)
    duplicates = faces[duplicate_sources].copy()
    duplicates[::2] = duplicates[::2, ::-1]  # half of them with the opposite winding
    degenerate_sources = rng.choice(candidates, DEGENERATES, replace=False)
    degenerate = faces[degenerate_sources].copy()
    degenerate[:, 1] = degenerate[:, 0]

    # Part and debris are shuffled; the injected copies follow their originals, so
    # that removing duplicates keeps the original face with its winding.
    scanned = np.vstack([faces, debris])
    order = rng.permutation(len(scanned))
    position = np.empty(len(scanned), dtype=np.int64)
    position[order] = np.arange(len(scanned))
    all_faces = np.vstack([scanned[order], duplicates, degenerate])
    return DirtyScan(
        mesh=RawMesh(all_vertices, all_faces.astype(np.int64)),
        clean_faces=np.sort(position[:part_faces]),
        debris_faces=np.sort(position[part_faces:]),
        flipped=np.sort(position[flipped]),
        holes=len(HOLE_CENTRES),
    )


def _vertex_normals_of_box(vertices: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Outward normals of the box; edge and corner vertices get the normalised sum."""
    size = np.array([100.0, 70.0, 20.0])
    normals = np.zeros_like(vertices)
    normals[np.isclose(vertices, 0.0)] = -1.0
    at_max = np.isclose(vertices, size)
    normals[at_max] = 1.0
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    return normals
