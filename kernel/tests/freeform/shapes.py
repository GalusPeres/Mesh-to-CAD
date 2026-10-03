"""Synthetic freeform test meshes with exact ground truth."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.normals import vertex_normals
from tests.synthetic import add_scanner_noise, random_rotation

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


def surface_height(x: FloatArray, y: FloatArray) -> FloatArray:
    """A bump on a gentle wave: the height field of the patch tests."""
    result: FloatArray = 6.0 * np.exp(-((x - 10.0) ** 2 + (y + 5.0) ** 2) / 150.0) + 2.0 * np.sin(
        x / 15.0
    )
    return result


@dataclass(frozen=True)
class HeightFieldScan:
    vertices: FloatArray
    faces: IntArray
    rotation: FloatArray
    offset: FloatArray

    def true_height_residual(self, points: FloatArray) -> FloatArray:
        """Vertical distance of posed points to the true surface (design frame)."""
        local = (points - self.offset) @ self.rotation
        result: FloatArray = local[:, 2] - surface_height(local[:, 0], local[:, 1])
        return result


def grid_faces(nx: int, ny: int) -> IntArray:
    index = np.arange(nx * ny).reshape(nx, ny)
    a, b = index[:-1, :-1].ravel(), index[1:, :-1].ravel()
    c, d = index[1:, 1:].ravel(), index[:-1, 1:].ravel()
    return np.concatenate([np.column_stack([a, b, c]), np.column_stack([a, c, d])]).astype(np.int64)


def height_field_scan(
    size: tuple[float, float] = (80.0, 60.0),
    step: float = 0.5,
    sigma: float = 0.02,
    seed: int = 5,
    height_scale: float = 1.0,
) -> HeightFieldScan:
    """An open surface patch over a rectangle, noisy and in a random pose."""
    rng = np.random.default_rng(seed)
    xs = np.arange(-size[0] / 2, size[0] / 2 + 1e-9, step)
    ys = np.arange(-size[1] / 2, size[1] / 2 + 1e-9, step)
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    vertices = np.column_stack(
        [xx.ravel(), yy.ravel(), height_scale * surface_height(xx, yy).ravel()]
    )
    faces = grid_faces(len(xs), len(ys))
    noisy = add_scanner_noise(vertices, vertex_normals(vertices, faces), sigma, rng)
    rotation = random_rotation(rng)
    offset = rng.uniform(-50.0, 50.0, 3)
    return HeightFieldScan(noisy @ rotation.T + offset, faces, rotation, offset)


def tube_radii(z: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Semi-axes of the elliptical tube sections at height z."""
    return 15.0 + 5.0 * np.sin(z / 12.0), 10.0 + 3.0 * np.cos(z / 15.0)


def tube_volume(start: float, end: float) -> float:
    """Exact volume of the tube between two heights (numerical quadrature of pi a b)."""
    z = np.linspace(start, end, 200_001)
    a, b = tube_radii(z)
    return float(np.trapezoid(math.pi * a * b, z))


def tube_scan(
    sigma: float = 0.02, seed: int = 7, ring_step: float = 0.5, ring_points: int = 240
) -> tuple[FloatArray, IntArray]:
    """A closed tube along Z (0..60 mm) with elliptic, drifting and twisting sections."""
    zs = np.arange(0.0, 60.0 + 1e-9, ring_step)
    angles = np.linspace(0.0, 2.0 * math.pi, ring_points, endpoint=False)
    rings = []
    for z in zs:
        a, b = tube_radii(np.asarray(z))
        twist = math.radians(30.0) * z / 60.0
        x, y = a * np.cos(angles), b * np.sin(angles)
        rotated_x = x * math.cos(twist) - y * math.sin(twist)
        rotated_y = x * math.sin(twist) + y * math.cos(twist)
        rings.append(np.column_stack([rotated_x + 0.005 * z * z, rotated_y, np.full_like(x, z)]))
    count, width = len(zs), len(angles)
    vertices = np.vstack([*rings, [[0.0, 0.0, 0.0]], [[0.005 * 3600.0, 0.0, 60.0]]])
    index = np.arange(count * width).reshape(count, width)
    faces = []
    for ring in range(count - 1):
        lower, upper = index[ring], index[ring + 1]
        faces += [
            np.column_stack([lower, np.roll(lower, -1), np.roll(upper, -1)]),
            np.column_stack([lower, np.roll(upper, -1), upper]),
        ]
    bottom, top = count * width, count * width + 1
    faces.append(np.column_stack([np.full(width, bottom), np.roll(index[0], -1), index[0]]))
    faces.append(np.column_stack([np.full(width, top), index[-1], np.roll(index[-1], -1)]))
    all_faces = np.vstack(faces).astype(np.int64)
    rng = np.random.default_rng(seed)
    noisy = add_scanner_noise(vertices, vertex_normals(vertices, all_faces), sigma, rng)
    return noisy, all_faces
