"""Whether points lie inside a scan: the generalised winding number.

The winding number of a point is the solid angle the triangles span as seen from
it, divided by 4π (Jacobson, Kavan, Sorkine-Hornung 2013,
doi:10.1145/2461912.2461916): 1 inside a closed, outward-oriented surface, 0
outside, and a smooth value in between near holes. Scans are rarely closed (an
open bottom, holes), so this is more robust than a ray parity test. Each
triangle's solid angle follows van Oosterom and Strackee (1983).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

_CHUNK = 250_000
"""Triangles per step; bounds the temporary arrays to a few tens of MB."""


def winding_numbers(vertices: FloatArray, faces: IntArray, points: FloatArray) -> FloatArray:
    """Generalised winding number of every point (k, 3) with respect to the triangles."""
    corners = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    result = np.zeros(len(points), dtype=np.float64)
    for index, point in enumerate(np.asarray(points, dtype=np.float64).reshape(-1, 3)):
        total = 0.0
        for start in range(0, len(corners), _CHUNK):
            total += _solid_angles(corners[start : start + _CHUNK] - point).sum()
        result[index] = total / (4.0 * np.pi)
    return result


def _solid_angles(corners: FloatArray) -> FloatArray:
    """Signed solid angle of each triangle (t, 3, 3), corners relative to the eye."""
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    la, lb, lc = (np.linalg.norm(v, axis=1) for v in (a, b, c))
    numerator = np.einsum("ij,ij->i", a, np.cross(b, c))
    denominator = (
        la * lb * lc
        + np.einsum("ij,ij->i", a, b) * lc
        + np.einsum("ij,ij->i", b, c) * la
        + np.einsum("ij,ij->i", c, a) * lb
    )
    angles: FloatArray = 2.0 * np.arctan2(numerator, denominator)
    return angles
