"""The coarse triangle cage the freeform surface is built on.

The scan is reduced with quadric decimation to the requested triangle count. The
decimated mesh must be an oriented 2-manifold with a single fan around every vertex
and the same closedness as the scan; decimation very rarely breaks that, so a failed
result is retried with slightly different target counts.

The decimated triangles are used as they are. Quadric decimation places more vertices
where the scan is curved and aligns long edges with flat directions; measured on the
Armadillo, edge flips for better angles raised the fitted RMS deviation by 35 % and
tangential relaxation by a factor of three, so neither is applied.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.subdivision import EdgeTopology, TopologyError, edge_topology

type IntArray = npt.NDArray[np.int64]
type Decimator = Callable[[FloatArray, IntArray, int], tuple[FloatArray, IntArray]]
"""Reduces (vertices, faces) to about `target` faces."""

MAX_PASSES = 4
RETRY_FACTORS = (1.0, 1.07, 0.93, 1.15, 0.87)


class CageError(ValueError):
    """No valid cage could be built from the scan."""


@dataclass(frozen=True)
class TriangleCage:
    vertices: FloatArray
    faces: IntArray
    closed: bool


def face_components(faces: IntArray, n_vertices: int) -> IntArray:
    """Component label per face; faces sharing a vertex belong to the same component."""
    n_faces = len(faces)
    incidence = sp.csr_matrix(
        (np.ones(faces.size), (np.repeat(np.arange(n_faces), 3), faces.ravel())),
        shape=(n_faces, n_vertices),
    )
    graph = sp.bmat([[None, incidence], [incidence.T, None]]).tocsr()
    _, labels = connected_components(graph, directed=False)
    face_labels: IntArray = labels[:n_faces].astype(np.int64)
    return face_labels


def compact(vertices: FloatArray, faces: IntArray) -> tuple[FloatArray, IntArray]:
    """Drop unreferenced vertices."""
    used = np.zeros(len(vertices), dtype=bool)
    used[faces.ravel()] = True
    new_index = np.cumsum(used) - 1
    return vertices[used], new_index[faces].astype(np.int64)


def fan_count(faces: IntArray, topology: EdgeTopology) -> IntArray:
    """Number of separate triangle fans around every vertex (1 for a manifold vertex)."""
    n_faces = len(faces)
    corner = np.arange(3 * n_faces).reshape(n_faces, 3)
    # Corners of the same vertex are linked when their faces share an edge at that vertex.
    shared = np.flatnonzero(~topology.boundary)
    face_a, face_b = topology.edge_faces[shared, 0], topology.edge_faces[shared, 1]
    links = []
    for end in range(2):
        vertex = topology.edges[shared, end]
        slot_a = np.argmax(faces[face_a] == vertex[:, None], axis=1)
        slot_b = np.argmax(faces[face_b] == vertex[:, None], axis=1)
        links.append(np.stack([corner[face_a, slot_a], corner[face_b, slot_b]], axis=1))
    pairs = np.concatenate(links)
    graph = sp.csr_matrix(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(3 * n_faces, 3 * n_faces)
    )
    _, labels = connected_components(graph, directed=False)
    vertex_of_corner = faces.ravel()
    unique_pairs = np.unique(np.stack([vertex_of_corner, labels], axis=1), axis=0)
    counts: IntArray = np.bincount(unique_pairs[:, 0], minlength=topology.n_vertices).astype(
        np.int64
    )
    return counts


def validate_cage(vertices: FloatArray, faces: IntArray) -> EdgeTopology:
    """Raise `TopologyError` unless the triangles form an oriented manifold without slivers."""
    topology = edge_topology(faces, len(vertices))
    if np.any(fan_count(faces, topology) > 1):
        raise TopologyError("a vertex joins separate fans")
    corners = vertices[faces]
    doubled_area = np.linalg.norm(
        np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1
    )
    if np.any(doubled_area <= 1e-12 * max(float(doubled_area.max(initial=0.0)), 1e-300)):
        raise TopologyError("a triangle has no area")
    return topology


def largest_component(vertices: FloatArray, faces: IntArray) -> tuple[FloatArray, IntArray, int]:
    """The component with the most faces, and how many other components were dropped."""
    labels = face_components(faces, len(vertices))
    counts = np.bincount(labels)
    keep = labels == int(np.argmax(counts))
    kept_vertices, kept_faces = compact(vertices, faces[keep])
    return kept_vertices, kept_faces, int(np.count_nonzero(counts)) - 1


def _decimate_to(
    vertices: FloatArray, faces: IntArray, target: int, decimate: Decimator
) -> tuple[FloatArray, IntArray]:
    """Decimate in passes until the face count is close to `target` or stops falling."""
    for _ in range(MAX_PASSES):
        if len(faces) <= target * 1.1:
            break
        reduced_vertices, reduced_faces = decimate(vertices, faces, target)
        progress = len(reduced_faces) < 0.95 * len(faces)
        vertices, faces = reduced_vertices, reduced_faces
        if not progress:
            break
    return compact(vertices, faces)


def decimated_cage(
    vertices: FloatArray,
    faces: IntArray,
    target: int,
    decimate: Decimator,
    check_cancelled: Callable[[], None] = lambda: None,
) -> TriangleCage:
    """A manifold triangle cage of about `target` faces for one connected scan component."""
    closed = not bool(np.any(edge_boundary_mask(faces, len(vertices))))
    for factor in RETRY_FACTORS:
        check_cancelled()
        cage_vertices, cage_faces = _decimate_to(
            vertices, faces, max(round(target * factor), 8), decimate
        )
        cage_vertices, cage_faces, _ = largest_component(cage_vertices, cage_faces)
        try:
            topology = validate_cage(cage_vertices, cage_faces)
        except TopologyError:
            continue
        if bool(np.any(topology.boundary)) == closed:
            continue
        return TriangleCage(cage_vertices, cage_faces, closed)
    raise CageError("decimation did not give a manifold cage")


def edge_boundary_mask(faces: IntArray, n_vertices: int) -> npt.NDArray[np.bool_]:
    """Per undirected edge: used by exactly one face (tolerates non-manifold edges)."""
    start = faces.ravel()
    end = np.roll(faces, -1, axis=1).ravel()
    keys = np.minimum(start, end) * n_vertices + np.maximum(start, end)
    _, counts = np.unique(keys, return_counts=True)
    mask: npt.NDArray[np.bool_] = counts == 1
    return mask
