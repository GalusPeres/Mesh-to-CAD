"""Synthetic organic scans for the surfacing tests: noisy sphere, torus and blob."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import trimesh

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class OrganicScan:
    vertices: FloatArray
    faces: IntArray
    sigma: float
    """Standard deviation of the added normal noise (mm)."""

    @property
    def diagonal(self) -> float:
        extent = self.vertices.max(axis=0) - self.vertices.min(axis=0)
        return float(np.linalg.norm(extent))


def _with_noise(vertices: FloatArray, faces: IntArray, sigma: float, seed: int) -> OrganicScan:
    normals = trimesh.Trimesh(vertices, faces, process=False).vertex_normals
    rng = np.random.default_rng(seed)
    noisy = vertices + normals * rng.normal(0.0, sigma, size=(len(vertices), 1))
    return OrganicScan(noisy, faces.astype(np.int64), sigma)


def sphere(radius: float = 20.0, sigma: float = 0.02, seed: int = 1) -> OrganicScan:
    mesh = trimesh.creation.icosphere(subdivisions=5, radius=radius)
    return _with_noise(np.asarray(mesh.vertices), np.asarray(mesh.faces), sigma, seed)


def torus(
    major: float = 30.0, minor: float = 10.0, sigma: float = 0.02, seed: int = 2
) -> OrganicScan:
    """A torus around z, 160 x 80 grid, counter-clockwise seen from outside."""
    nu, nv = 160, 80
    u, v = np.meshgrid(
        np.linspace(0, 2 * np.pi, nu, endpoint=False),
        np.linspace(0, 2 * np.pi, nv, endpoint=False),
        indexing="ij",
    )
    ring = major + minor * np.cos(v)
    vertices = np.stack([ring * np.cos(u), ring * np.sin(u), minor * np.sin(v)], axis=-1)
    i, j = np.meshgrid(np.arange(nu), np.arange(nv), indexing="ij")
    a = i * nv + j
    b = ((i + 1) % nu) * nv + j
    c = ((i + 1) % nu) * nv + (j + 1) % nv
    d = i * nv + (j + 1) % nv
    faces = np.concatenate(
        [np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)]
    )
    return _with_noise(vertices.reshape(-1, 3), faces, sigma, seed)


def blob(radius: float = 25.0, sigma: float = 0.03, seed: int = 3) -> OrganicScan:
    """A lumpy closed surface: a sphere with smooth radial bumps and dents."""
    mesh = trimesh.creation.icosphere(subdivisions=5, radius=1.0)
    direction = np.asarray(mesh.vertices)
    x, y, z = direction.T
    bumps = 0.18 * np.sin(3 * x) * np.cos(2 * y) + 0.12 * np.cos(4 * z + x) + 0.25 * x * z
    vertices = direction * (radius * (1.0 + bumps))[:, None]
    return _with_noise(vertices, np.asarray(mesh.faces), sigma, seed)
