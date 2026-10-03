"""Clean quad control nets from scans by field-aligned remeshing (Instant Meshes).

Instant Meshes (Jakob et al. 2015) optimises an orientation and a position field on
the scan and extracts a quad mesh whose edges follow the principal directions, with
few irregular vertices. Its pure-quad output subdivides the extracted quad-dominant
mesh once, so it has about four quads per requested vertex. The library holds the
GIL, cannot be interrupted and prints to stdout, so it runs in a child process
(`mesh/child.py`).

The result is cleaned into a net the surfacing pipeline accepts: quads with four
distinct corners, no unused vertices, only the largest connected part, consistently
oriented and facing the same way as the scan. Its open border is laid onto the rim of
the triangles (`rim.py`), which the extracted quads stop short of.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray
from m2c_kernel.mesh.child import run_in_child
from m2c_kernel.surfacing.rim import snap_border_to_rim
from m2c_kernel.surfacing.subdivision import TopologyError, edge_topology

type IntArray = npt.NDArray[np.int64]

QUADS_PER_VERTEX = 4.0
"""Pure-quad output of Instant Meshes per requested vertex (one regular subdivision)."""
MIN_QUADS = 16
MAX_QUADS = 20_000


class QuadMeshError(Exception):
    """Remeshing produced no usable quad net."""


@dataclass(frozen=True)
class QuadNet:
    """A quad control net: (n, 3) vertices and (q, 4) counter-clockwise quads."""

    vertices: FloatArray
    quads: IntArray


Remesher = Callable[[FloatArray, IntArray, int, float], tuple[FloatArray, IntArray]]
"""(vertices, faces, vertex count, crease angle in degrees) -> raw quad mesh."""


def quad_net(
    vertices: FloatArray,
    faces: IntArray,
    normals: FloatArray,
    target_quads: int,
    *,
    crease_deg: float = 0.0,
    remesh: Remesher | None = None,
    check_cancelled: Callable[[], None] = lambda: None,
) -> QuadNet:
    """A field-aligned quad net with about `target_quads` quads on the triangle mesh.

    Args:
        vertices: (n, 3) scan vertices.
        faces: (m, 3) triangles.
        normals: (n, 3) unit vertex normals, pointing out of the material.
        target_quads: Wanted quad count (the result differs by up to about 20 %).
        crease_deg: Dihedral angle above which scan edges are kept as sharp feature
            lines the quad edges align to; 0 disables feature alignment.
        remesh: Replaces the child-process remesher (tests).
        check_cancelled: Raises when the job is cancelled; the child process is killed.

    Raises:
        QuadMeshError: The remesher failed or returned no manifold quad net.
    """
    target = int(np.clip(target_quads, MIN_QUADS, MAX_QUADS))
    vertex_count = max(4, round(target / QUADS_PER_VERTEX))
    run = remesh or _child_process_remesher(check_cancelled)
    raw_vertices, raw_quads = run(vertices, faces, vertex_count, crease_deg)
    net = clean_quad_net(raw_vertices, raw_quads, vertices, normals)
    return QuadNet(snap_border_to_rim(net.vertices, net.quads, vertices, faces), net.quads)


def clean_quad_net(
    raw_vertices: FloatArray, raw_quads: IntArray, scan_points: FloatArray, scan_normals: FloatArray
) -> QuadNet:
    """Keep valid quads of the largest part, compact, check topology, face outwards."""
    quads = np.asarray(raw_quads, dtype=np.int64).reshape(-1, 4)
    if len(quads) == 0:
        raise QuadMeshError("the remesher returned no faces")
    distinct = np.array([len(set(quad)) == 4 for quad in quads.tolist()], dtype=bool)
    quads = quads[distinct]
    quads = _largest_part(quads, len(raw_vertices))
    used, remapped = np.unique(quads, return_inverse=True)
    net_vertices = np.asarray(raw_vertices, dtype=np.float64)[used]
    quads = remapped.reshape(-1, 4).astype(np.int64)
    if len(quads) < MIN_QUADS:
        raise QuadMeshError(f"only {len(quads)} quads")
    try:
        edge_topology(quads, len(net_vertices))
    except TopologyError as error:
        raise QuadMeshError(str(error)) from error
    if _faces_inwards(net_vertices, quads, scan_points, scan_normals):
        quads = quads[:, ::-1].copy()
    return QuadNet(net_vertices, quads)


def _largest_part(quads: IntArray, n_vertices: int) -> IntArray:
    """Quads of the largest edge-connected part (vertex sharing alone does not connect)."""
    start = quads.ravel()
    end = np.roll(quads, -1, axis=1).ravel()
    keys = np.minimum(start, end) * n_vertices + np.maximum(start, end)
    _, edge_of = np.unique(keys, return_inverse=True)
    face_of = np.repeat(np.arange(len(quads)), 4)
    incidence = sp.csr_matrix(
        (np.ones(len(face_of)), (face_of, edge_of)), shape=(len(quads), edge_of.max() + 1)
    )
    adjacency = incidence @ incidence.T
    _, labels = connected_components(adjacency, directed=False)
    counts = np.bincount(labels)
    result: IntArray = quads[labels == np.argmax(counts)]
    return result


def _faces_inwards(
    vertices: FloatArray, quads: IntArray, scan_points: FloatArray, scan_normals: FloatArray
) -> bool:
    """Whether most of the net area faces against the normals of the nearest scan points."""
    p = vertices
    normals = np.cross(p[quads[:, 2]] - p[quads[:, 0]], p[quads[:, 3]] - p[quads[:, 1]])
    centres = p[quads].mean(axis=1)
    _, nearest = cKDTree(scan_points).query(centres, workers=-1)
    agreement = np.einsum("ij,ij->i", normals, scan_normals[nearest])
    return float(agreement.sum()) < 0.0


def _child_process_remesher(check_cancelled: Callable[[], None]) -> Remesher:
    def run(
        vertices: FloatArray, faces: IntArray, vertex_count: int, crease_deg: float
    ) -> tuple[FloatArray, IntArray]:
        return run_in_child(
            remesh_in_process,
            (vertices.astype(np.float32), faces.astype(np.uint32), vertex_count, crease_deg),
            check_cancelled,
        )

    return run


def remesh_in_process(
    vertices: npt.NDArray[np.float32],
    faces: npt.NDArray[np.uint32],
    vertex_count: int,
    crease_deg: float,
) -> tuple[FloatArray, IntArray]:
    """Instant Meshes in the calling process (the kernel calls it in a child process)."""
    import pynanoinstantmeshes

    out_vertices, out_faces = pynanoinstantmeshes.remesh(
        np.ascontiguousarray(vertices, dtype=np.float32),
        np.ascontiguousarray(faces, dtype=np.uint32),
        int(vertex_count),
        rosy=4,
        posy=4,
        creaseAngle=float(crease_deg),
        align_to_boundaries=True,
        smooth_iter=2,
        deterministic=True,
    )
    return np.asarray(out_vertices, np.float64), np.asarray(out_faces, np.int64)
