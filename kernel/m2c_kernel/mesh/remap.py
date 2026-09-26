"""Carrying face sets and region labels over to a new working mesh.

Every operation that changes the faces of the scan returns a face index map
`new_to_old`: for each new face the index of the face it came from, or -1 for a
new face without a source (hole filling). Operations that keep, drop or append
faces (delete, degenerate and duplicate removal, small parts, hole filling)
return an exact map. Only decimation, which merges faces, builds the map by
nearest centroid (`nearest_centroid_map`). New faces never join existing face
sets, so synthetic geometry cannot enter fits.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray

type IndexArray = npt.NDArray[np.int64]


def remap_face_set(face_set: IndexArray, new_to_old: IndexArray, old_face_count: int) -> IndexArray:
    """Indices of the new faces whose source face belongs to `face_set`."""
    member = np.zeros(old_face_count, dtype=bool)
    member[face_set] = True
    has_source = new_to_old >= 0
    selected = has_source & member[np.where(has_source, new_to_old, 0)]
    return np.flatnonzero(selected).astype(np.int64)


def remap_labels(labels: npt.NDArray[np.uint16], new_to_old: IndexArray) -> npt.NDArray[np.uint16]:
    """Per-face labels on the new mesh; faces without a source are unassigned (0)."""
    has_source = new_to_old >= 0
    result = np.zeros(len(new_to_old), dtype=np.uint16)
    result[has_source] = labels[new_to_old[has_source]]
    return result


def nearest_centroid_map(old_centroids: FloatArray, new_centroids: FloatArray) -> IndexArray:
    """Approximate `new_to_old` map for operations that merge faces (decimation)."""
    from scipy.spatial import cKDTree

    _, nearest = cKDTree(old_centroids).query(new_centroids, k=1, workers=-1)
    return np.asarray(nearest, dtype=np.int64)
