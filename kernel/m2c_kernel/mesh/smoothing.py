"""Taubin smoothing of the scan for display and scan export.

Smoothing never feeds fits or deviation maps: least squares already averages the
noise, while smoothing rounds every crease. The working mesh stays unsmoothed and
`scan.display_smoothing` holds the iteration count. Measurements:
`.work/research/algorithms-mesh.md` 1.4.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp

from m2c_kernel.geometry import FloatArray

LAMBDA = 0.5
MU = -0.53
"""Shrink and inflate factors; `MU < -LAMBDA` keeps the volume (pass band about 0.11)."""

MAX_ITERATIONS = 20


def uniform_laplacian(faces: npt.NDArray[np.int64], vertex_count: int) -> sp.csr_matrix:
    """Row-normalised vertex adjacency: `W @ X` averages the neighbours of every vertex."""
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    size = (vertex_count, vertex_count)
    adjacency = sp.coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=size)
    adjacency = adjacency.tocsr()
    adjacency.data[:] = 1.0  # duplicate entries were summed
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    weights: sp.csr_matrix = (sp.diags(1.0 / np.maximum(degree, 1.0)) @ adjacency).tocsr()
    return weights


def taubin(vertices: FloatArray, faces: npt.NDArray[np.int64], iterations: int) -> FloatArray:
    """Vertex positions after `iterations` shrink-and-inflate pairs."""
    smoothed = np.array(vertices, dtype=np.float64)
    if iterations <= 0 or len(faces) == 0:
        return smoothed
    weights = uniform_laplacian(faces, len(smoothed))
    for _ in range(iterations):
        smoothed += LAMBDA * (weights @ smoothed - smoothed)
        smoothed += MU * (weights @ smoothed - smoothed)
    return smoothed
