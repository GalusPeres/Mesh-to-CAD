"""Lay an auto net's open border onto the rim of the triangles it covers.

Instant Meshes extracts quads only where a whole quad fits, so the border of a net
on a selection (or on an open scan) stays up to a quad or two short of the
selection's edge, with notches where single quads are missing. Such a border cannot
be pushed past a reference face within a sensible reach, and trimming then finds no
closed region. QuickSurface's auto net ends on the selection's edge ("Improve holes
boundary"); so does ours.

Every border point's limit point moves to the nearest point of the rim. The border
of a Catmull-Clark net is a cubic B-spline of the border control points alone, so
solving those points puts the limit border exactly there; inner points stay and the
following fit evens out the last rows. Rim loops shorter than a few net edges (small
holes the net spans) are ignored, and so are rim points farther than a few net edges
(the net does not reach that part of the selection at all).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.subdivision import edge_topology, limit_matrix

type IntArray = npt.NDArray[np.int64]

PASSES = 3
"""The nearest rim point changes as the border moves; a few passes settle it."""
REACH_EDGES = 3.0
"""Border points move at most this many mean net edges."""
MIN_LOOP_EDGES = 6.0
"""Rim loops shorter than this many mean net edges are holes the net spans."""
RIM_STEP_EDGES = 0.1
"""Rim sample spacing in mean net edges."""


def snap_border_to_rim(
    cage: FloatArray, quads: IntArray, vertices: FloatArray, faces: IntArray
) -> FloatArray:
    """The net with its open border on the open edges of the triangles (n, 3) / (m, 3)."""
    topology = edge_topology(quads, len(cage))
    if not np.any(topology.boundary):
        return cage
    lengths = np.linalg.norm(cage[topology.edges[:, 0]] - cage[topology.edges[:, 1]], axis=1)
    edge = float(np.mean(lengths))
    rim = rim_points(vertices, faces, min_loop=MIN_LOOP_EDGES * edge, step=RIM_STEP_EDGES * edge)
    if len(rim) == 0:
        return cage
    tree = cKDTree(rim)
    border = np.unique(topology.edges[topology.boundary].ravel())
    limits = limit_matrix(quads, len(cage)).tocsr()[border]
    system = limits[:, border].tocsc()
    result = cage.copy()
    for _ in range(PASSES):
        current = limits @ result
        distance, nearest = tree.query(current, workers=-1)
        moves = rim[nearest] - current
        moves[distance > REACH_EDGES * edge] = 0.0
        if not np.any(moves):
            break
        offsets = np.column_stack([spla.spsolve(system, moves[:, axis]) for axis in range(3)])
        result[border] += offsets
    return result


def rim_points(
    vertices: FloatArray, faces: IntArray, *, min_loop: float, step: float
) -> FloatArray:
    """Points along the open edges of the triangles, on rim loops at least `min_loop` long."""
    sides = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    keys, counts = np.unique(sides[:, 0] * len(vertices) + sides[:, 1], return_counts=True)
    open_keys = keys[counts == 1]
    if len(open_keys) == 0:
        return np.empty((0, 3))
    ends = np.column_stack([open_keys // len(vertices), open_keys % len(vertices)])
    lengths = np.linalg.norm(vertices[ends[:, 0]] - vertices[ends[:, 1]], axis=1)
    graph = sp.coo_matrix(
        (np.ones(len(ends)), (ends[:, 0], ends[:, 1])), shape=(len(vertices),) * 2
    )
    _, labels = connected_components(graph, directed=False)
    loop_length = np.bincount(labels[ends[:, 0]], weights=lengths)
    long_enough = loop_length[labels[ends[:, 0]]] >= min_loop
    ends, lengths = ends[long_enough], lengths[long_enough]
    pieces = np.maximum(1, np.ceil(lengths / step).astype(np.int64))
    owner = np.repeat(np.arange(len(ends)), pieces)
    share = (np.arange(len(owner)) - np.repeat(np.cumsum(pieces) - pieces, pieces)) / pieces[owner]
    start, end = vertices[ends[owner, 0]], vertices[ends[owner, 1]]
    points: FloatArray = start + (end - start) * share[:, None]
    return points
