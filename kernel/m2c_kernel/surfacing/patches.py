"""Bicubic B-spline patches that interpolate the limit surface of every cage quad.

Each patch interpolates an n x n grid of limit samples at uniform parameters, with
the knots placed by de Boor's averaging. All patches share the same knots and the
same interpolation matrix N, so the poles of every patch are `N^-1 Q N^-T` in one
batched product.

Why neighbouring patches meet exactly: with clamped knots, the boundary curve of an
interpolating tensor-product spline depends only on the boundary row of samples,
and the knots are symmetric under t -> 1 - t. Two patches that share an edge share
its samples (the same limit points, possibly in reverse order), so their boundary
curves are the same curve up to rounding.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline

from m2c_kernel.geometry import FloatArray

DEGREE = 3


def interpolation_knots(count: int) -> FloatArray:
    """Clamped cubic knots for `count` samples at uniform parameters (de Boor averaging)."""
    params = np.linspace(0.0, 1.0, count)
    interior = np.array([params[j : j + DEGREE].mean() for j in range(1, count - DEGREE)])
    knots: FloatArray = np.concatenate([np.zeros(DEGREE + 1), interior, np.ones(DEGREE + 1)])
    return knots


def basis(knots: FloatArray, parameters: FloatArray, derivative: int = 0) -> FloatArray:
    """(len(parameters), n) values of all basis functions (or their derivatives)."""
    count = len(knots) - DEGREE - 1
    values: FloatArray = BSpline(knots, np.eye(count), DEGREE)(parameters, nu=derivative)
    return values


@dataclass(frozen=True)
class PatchNetwork:
    """Poles of all patches; patch i belongs to cage quad i.

    Attributes:
        poles: (p, n, n, 3); axis 1 is u (quad corner 0 -> 1), axis 2 is v (0 -> 3).
        knots: Clamped knot vector shared by u and v and by all patches.
    """

    poles: FloatArray
    knots: FloatArray

    @property
    def pole_count(self) -> int:
        return int(self.poles.shape[1])

    def evaluate(self, parameters: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Points and unit normals on the grid `parameters x parameters` of every patch."""
        values = basis(self.knots, parameters)
        slopes = basis(self.knots, parameters, derivative=1)
        points = np.einsum("ia,pabk,jb->pijk", values, self.poles, values)
        along_u = np.einsum("ia,pabk,jb->pijk", slopes, self.poles, values)
        along_v = np.einsum("ia,pabk,jb->pijk", values, self.poles, slopes)
        normals = np.cross(along_u, along_v)
        normals /= np.maximum(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-300)
        return points, normals


def interpolate_patches(samples: FloatArray) -> PatchNetwork:
    """Patches through (p, n, n, 3) sample grids taken at uniform parameters."""
    count = samples.shape[1]
    knots = interpolation_knots(count)
    matrix = basis(knots, np.linspace(0.0, 1.0, count))
    inverse = np.linalg.inv(matrix)
    poles = np.einsum("ia,pabk,jb->pijk", inverse, samples, inverse)
    return PatchNetwork(poles=poles, knots=knots)
