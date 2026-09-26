"""Face and vertex normals, and local quadric ("jet") fits for normals, curvature and noise.

Per-triangle or 1-ring estimators inherit the tessellation of a scan and are
dominated by its smallest triangles. The jet fit works at a spatial scale
instead: it fits a height function to the k nearest neighbours on a voxel
subsample and maps the result back to all vertices. Its median residual is a
usable estimate of the scanner noise. Measurements:
`.work/research/algorithms-mesh.md` 2.1 and 2.2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray
from m2c_kernel.mesh.topology import pack_rows

DEFAULT_CELL_MM = 0.5
DEFAULT_NEIGHBOURS = 24
NOISE_SAMPLES = 50_000


def face_normals(
    vertices: FloatArray, faces: npt.NDArray[np.int64]
) -> tuple[FloatArray, FloatArray]:
    """Unit face normals and face areas."""
    cross = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]
    )
    doubled_area = np.linalg.norm(cross, axis=1)
    normals: FloatArray = cross / np.maximum(doubled_area, 1e-300)[:, None]
    return normals, 0.5 * doubled_area


def vertex_normals(vertices: FloatArray, faces: npt.NDArray[np.int64]) -> FloatArray:
    """Area-weighted vertex normals.

    Vertices whose face normals cancel out (folds left by decimation) take the
    normal of one incident face; unreferenced vertices get +Z.
    """
    cross = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]
    )
    summed = np.zeros_like(vertices)
    for corner in range(3):
        for axis in range(3):
            summed[:, axis] += np.bincount(
                faces[:, corner], weights=cross[:, axis], minlength=len(vertices)
            )
    length = np.linalg.norm(summed, axis=1)
    degenerate = length <= 1e-12 * max(float(length.max(initial=0.0)), 1e-300)
    if degenerate.any():
        fallback = np.tile([0.0, 0.0, 1.0], (len(vertices), 1))
        fallback[faces.ravel()] = np.repeat(cross, 3, axis=0)
        summed[degenerate] = fallback[degenerate]
        length = np.linalg.norm(summed, axis=1)
    result: FloatArray = summed / np.maximum(length, 1e-300)[:, None]
    return result


def voxel_subsample(points: FloatArray, cell: float) -> npt.NDArray[np.int64]:
    """Index of one point per occupied cubic cell of size `cell`."""
    key = pack_rows(np.floor((points - points.min(axis=0)) / cell))
    first: npt.NDArray[np.int64] = np.unique(key, return_index=True)[1]
    return first


@dataclass(frozen=True)
class JetFit:
    """Per-vertex results of the jet fit.

    Attributes:
        normals: Refined unit normals (median error about 1 degree on a noisy scan).
        k1: Larger principal curvature (1/mm, positive = convex).
        k2: Smaller principal curvature.
        residual: RMS residual of the local fit; rises sharply near creases.
    """

    normals: FloatArray
    k1: FloatArray
    k2: FloatArray
    residual: FloatArray

    @property
    def noise(self) -> float:
        """Scanner noise estimate: the median residual (mm)."""
        return float(np.median(self.residual))


def jet_fit(
    vertices: FloatArray,
    normals: FloatArray,
    cell: float = DEFAULT_CELL_MM,
    neighbours: int = DEFAULT_NEIGHBOURS,
    chunk: int = 200_000,
) -> JetFit:
    """Fit `z = (a x^2 + 2 b x y + c y^2) / 2 + d x + e y + f` around every subsample point.

    `normals` are rough vertex normals that define the local frames. The fit
    radius is about `cell * sqrt(neighbours / pi)`; features narrower than twice
    that get meaningless curvature.
    """
    sample = voxel_subsample(vertices, cell)
    points, frame_normals = vertices[sample], normals[sample]
    k = min(neighbours, len(points))
    tree = cKDTree(points)
    _, neighbour_index = tree.query(points, k=k, workers=-1)
    k1 = np.empty(len(points))
    k2 = np.empty(len(points))
    refined = np.empty_like(points)
    residual = np.empty(len(points))
    for start in range(0, len(points), chunk):
        part = slice(start, start + chunk)
        n, u, w, coef, residual[part] = _local_quadrics(
            points, frame_normals[part], points[part], neighbour_index[part]
        )
        a, b, c, d, e = coef[:, :5].T
        g = np.sqrt(1 + d * d + e * e)
        i11, i12, i22 = 1 + d * d, d * e, 1 + e * e
        det = i11 * i22 - i12 * i12
        l_, m_, n_ = -a / g, -b / g, -c / g
        s11 = (i22 * l_ - i12 * m_) / det
        s12 = (i22 * m_ - i12 * n_) / det
        s21 = (-i12 * l_ + i11 * m_) / det
        s22 = (-i12 * m_ + i11 * n_) / det
        trace, determinant = s11 + s22, s11 * s22 - s12 * s21
        spread = np.sqrt(np.maximum(trace * trace / 4 - determinant, 0.0))
        k1[part], k2[part] = trace / 2 + spread, trace / 2 - spread
        tilted = n - d[:, None] * u - e[:, None] * w
        refined[part] = tilted / np.linalg.norm(tilted, axis=1)[:, None]
    _, owner = tree.query(vertices, k=1, workers=-1)
    return JetFit(normals=refined[owner], k1=k1[owner], k2=k2[owner], residual=residual[owner])


@dataclass(frozen=True)
class NoiseEstimate:
    """Scanner noise (median jet residual, in the unit of the vertices).

    `sample_share` is the share of vertices that became subsample points; near 1
    the cell is below the vertex spacing, and every finer cell gives the same value.
    """

    noise: float | None
    sample_share: float


def estimate_noise(
    vertices: FloatArray,
    normals: FloatArray,
    rng: np.random.Generator,
    cell: float = DEFAULT_CELL_MM,
    neighbours: int = DEFAULT_NEIGHBOURS,
    max_samples: int = NOISE_SAMPLES,
) -> NoiseEstimate:
    """The noise measure of `jet_fit` from at most `max_samples` local fits.

    The median over a random subset of the subsample points agrees with the
    median over all of them to well below a micrometre, at a fraction of the cost.
    """
    sample = voxel_subsample(vertices, cell)
    share = len(sample) / max(len(vertices), 1)
    if len(sample) < 2 * neighbours:
        return NoiseEstimate(None, share)
    points, frame_normals = vertices[sample], normals[sample]
    centres = np.arange(len(points))
    if len(points) > max_samples:
        centres = np.sort(rng.choice(len(points), max_samples, replace=False))
    _, neighbour_index = cKDTree(points).query(points[centres], k=neighbours, workers=-1)
    *_, residual = _local_quadrics(points, frame_normals[centres], points[centres], neighbour_index)
    return NoiseEstimate(float(np.median(residual)), share)


def _local_quadrics(
    points: FloatArray,
    frame_normals: FloatArray,
    centres: FloatArray,
    neighbour_index: npt.NDArray[np.int64],
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """Least-squares height quadrics in the frame (u, w, n) of each centre.

    Returns the frames, the six coefficients per centre and the RMS residual.
    """
    n = frame_normals
    helper = np.where(np.abs(n[:, :1]) < 0.9, [[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u, axis=1)[:, None]
    w = np.cross(n, u)
    offsets = points[neighbour_index] - centres[:, None, :]
    x = (offsets * u[:, None]).sum(axis=2)
    y = (offsets * w[:, None]).sum(axis=2)
    z = (offsets * n[:, None]).sum(axis=2)
    design = np.stack([0.5 * x * x, x * y, 0.5 * y * y, x, y, np.ones_like(x)], axis=2)
    normal_matrix = np.einsum("mki,mkj->mij", design, design) + np.eye(6) * 1e-12
    rhs = np.einsum("mki,mk->mi", design, z)
    coef = np.linalg.solve(normal_matrix, rhs[..., None])[..., 0]
    residual = np.sqrt(((np.einsum("mki,mi->mk", design, coef) - z) ** 2).mean(axis=1))
    return n, u, w, coef, residual
