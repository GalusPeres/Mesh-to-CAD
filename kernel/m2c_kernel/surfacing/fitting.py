"""Least-squares fit of a Catmull-Clark control cage to the scan.

The limit samples are `A @ X` for cage positions X (see `subdivision.py`), so every
iteration is a sparse linear least-squares problem:

- surface to scan: every limit sample should lie on the tangent plane of its nearest
  scan point (the target is the sample projected onto that plane);
- scan to surface: every scan point pulls its nearest limit sample along the sample
  normal onto the point's level, so narrow protrusions of the scan are not skipped;
- fairness: `smoothing * |L X|^2` with the uniform Laplacian of the cage;
- damping: `|L (X - X_prev)|^2` keeps each update smooth without biasing the result
  (it vanishes at convergence).

Pairs whose normals disagree by more than about 70 degrees, or whose distance is far
above the typical one, are ignored: they are correspondences with the wrong side of
a thin part.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray
from m2c_kernel.surfacing.subdivision import (
    PatchHierarchy,
    edge_topology,
    quad_vertex_normals,
)

type IntArray = npt.NDArray[np.int64]

NORMAL_AGREEMENT = 0.3
"""Minimum cosine between a sample normal and a scan normal for a valid pair."""
OUTLIER_FACTOR = 5.0
"""Pairs farther than this multiple of the median pair distance are ignored."""
DAMPING = 0.05
STAY = 1e-6


@dataclass(frozen=True)
class ScanSamples:
    """Scan points with unit normals and a KD-tree over the points."""

    points: FloatArray
    normals: FloatArray
    tree: cKDTree


def scan_samples(points: FloatArray, normals: FloatArray) -> ScanSamples:
    return ScanSamples(points, normals, cKDTree(points))


@dataclass(frozen=True)
class FitProgress:
    iteration: int
    iterations: int
    rms: float


def cage_laplacian(quads: IntArray, n_vertices: int) -> sp.csr_matrix:
    """Uniform Laplacian `I - mean(neighbours)` over the cage edges."""
    topology = edge_topology(quads, n_vertices)
    edges = topology.edges
    rows = np.concatenate([edges[:, 0], edges[:, 1]])
    cols = np.concatenate([edges[:, 1], edges[:, 0]])
    adjacency = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_vertices, n_vertices))
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    laplacian = sp.identity(n_vertices) - sp.diags(1.0 / np.maximum(degree, 1.0)) @ adjacency
    return laplacian.tocsr()


def _surface_targets(
    samples: FloatArray, normals: FloatArray, scan: ScanSamples
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Foot points on the scan's tangent planes, their weights and the pair distances."""
    _, index = scan.tree.query(samples, workers=-1)
    nearest, scan_normal = scan.points[index], scan.normals[index]
    offset = np.einsum("ij,ij->i", samples - nearest, scan_normal)
    targets = samples - offset[:, None] * scan_normal
    agree = np.einsum("ij,ij->i", normals, scan_normal) > NORMAL_AGREEMENT
    return targets, agree.astype(np.float64), np.abs(offset)


def _scan_targets(
    samples: FloatArray, normals: FloatArray, scan: ScanSamples
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Per sample: the mean level of the scan points that chose it, their count and distances."""
    tree = cKDTree(samples)
    _, index = tree.query(scan.points, workers=-1)
    sample_normal = normals[index]
    offset = np.einsum("ij,ij->i", scan.points - samples[index], sample_normal)
    agree = np.einsum("ij,ij->i", sample_normal, scan.normals) > NORMAL_AGREEMENT
    count = np.bincount(index[agree], minlength=len(samples)).astype(np.float64)
    offset_sum = np.bincount(index[agree], weights=offset[agree], minlength=len(samples))
    mean_offset = offset_sum / np.maximum(count, 1.0)
    targets = samples + mean_offset[:, None] * normals
    return targets, count, np.abs(offset[agree])


def fit_cage(
    cage: FloatArray,
    quads: IntArray,
    hierarchy: PatchHierarchy,
    scan: ScanSamples,
    *,
    smoothing: float,
    iterations: int,
    check_cancelled: Callable[[], None] = lambda: None,
    progress: Callable[[FitProgress], None] = lambda _: None,
) -> FloatArray:
    """Move the cage vertices so that the limit surface follows the scan.

    Args:
        cage: (n, 3) initial cage positions.
        quads: (q, 4) cage quads; `hierarchy` must be built from them.
        hierarchy: Sample grids of the limit surface used for the fit.
        scan: Target points with normals.
        smoothing: Weight of the fairness term per cage vertex (0 disables it).
        iterations: Number of correspondence updates.
        check_cancelled: Raises when the job is cancelled.
        progress: Called after every iteration with the RMS of the pair distances.
    """
    sample_matrix = hierarchy.sample_matrix()
    sample_matrix_t = sample_matrix.T.tocsr()
    cells = hierarchy.cells
    laplacian = cage_laplacian(quads, len(cage))
    smoothness = (laplacian.T @ laplacian).tocsr()
    samples_per_vertex = sample_matrix.shape[0] / len(cage)
    positions = np.array(cage, dtype=np.float64)
    for iteration in range(iterations):
        check_cancelled()
        samples = sample_matrix @ positions
        normals = quad_vertex_normals(samples, cells)
        surface_targets, surface_weight, surface_distance = _surface_targets(samples, normals, scan)
        check_cancelled()
        scan_targets, scan_count, scan_distance = _scan_targets(samples, normals, scan)

        reference = float(np.median(np.concatenate([surface_distance, scan_distance])))
        limit = OUTLIER_FACTOR * max(reference, 1e-9)
        surface_weight[surface_distance > limit] = 0.0
        scan_weight = scan_count / max(float(scan_count[scan_count > 0].mean()), 1.0)
        scan_weight[np.linalg.norm(scan_targets - samples, axis=1) > limit] = 0.0

        weight = surface_weight + scan_weight
        targets = (
            surface_weight[:, None] * surface_targets + scan_weight[:, None] * scan_targets
        ) / np.maximum(weight, 1e-12)[:, None]

        # The tiny identity term keeps vertices without any valid pair in place.
        stay = STAY * sp.identity(len(positions))
        regular = samples_per_vertex * ((smoothing + DAMPING) * smoothness + stay)
        system = (sample_matrix_t @ sp.diags(weight) @ sample_matrix + regular).tocsc()
        rhs = sample_matrix_t @ (weight[:, None] * targets)
        rhs += samples_per_vertex * (DAMPING * (smoothness @ positions) + STAY * positions)
        positions = splu(system).solve(rhs)
        rms = float(np.sqrt(np.mean(np.concatenate([surface_distance, scan_distance]) ** 2)))
        progress(FitProgress(iteration + 1, iterations, rms))
    return positions
