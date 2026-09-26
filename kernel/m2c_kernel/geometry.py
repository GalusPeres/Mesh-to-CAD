"""Small vector helpers and geometric type aliases shared across the kernel."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

type Vec3 = tuple[float, float, float]
type Matrix4 = tuple[float, ...]
"""4 x 4 transform as 16 numbers in row-major order."""

type FloatArray = npt.NDArray[np.float64]

IDENTITY: Matrix4 = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def vec3(values: npt.ArrayLike) -> Vec3:
    """Convert a 3-vector to a tuple of Python floats (for wire types)."""
    x, y, z = np.asarray(values, dtype=np.float64).reshape(3)
    return (float(x), float(y), float(z))


def unit(vectors: npt.ArrayLike) -> FloatArray:
    """Normalise vectors along the last axis; zero vectors stay zero."""
    array = np.asarray(vectors, dtype=np.float64)
    length = np.linalg.norm(array, axis=-1, keepdims=True)
    return array / np.where(length == 0.0, 1.0, length)


def frame_from_axis(axis: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
    """Two unit vectors that complete `axis` to a right-handed orthonormal frame."""
    a = unit(axis)
    helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = unit(np.cross(a, helper))
    e2 = np.cross(a, e1)
    return e1, e2


def matrix_array(matrix: Matrix4) -> FloatArray:
    """A row-major `Matrix4` as a 4 x 4 array."""
    return np.asarray(matrix, dtype=np.float64).reshape(4, 4)


def matrix_tuple(matrix: npt.ArrayLike) -> Matrix4:
    """A 4 x 4 array as a row-major `Matrix4`."""
    return tuple(float(value) for value in np.asarray(matrix, dtype=np.float64).reshape(16))


def transform_points(matrix: Matrix4, points: npt.ArrayLike) -> FloatArray:
    """Apply a rigid 4 x 4 transform to (n, 3) points."""
    m = matrix_array(matrix)
    p = np.asarray(points, dtype=np.float64)
    result: FloatArray = p @ m[:3, :3].T + m[:3, 3]
    return result
