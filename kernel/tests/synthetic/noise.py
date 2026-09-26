"""Scanner-like noise and random rigid poses."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

type FloatArray = npt.NDArray[np.float64]


def add_scanner_noise(
    vertices: FloatArray,
    normals: FloatArray,
    sigma: float,
    rng: np.random.Generator,
    spike_fraction: float = 0.0,
    spike_magnitude: tuple[float, float] = (0.15, 0.3),
) -> FloatArray:
    """Gaussian displacement along the normal plus sparse spikes (the default test noise).

    The acceptance targets use sigma 0.03 mm with 0.1 % spikes of 0.15-0.3 mm.
    """
    noisy = vertices + normals * rng.normal(0.0, sigma, size=(len(vertices), 1))
    count = int(spike_fraction * len(vertices))
    if count:
        chosen = rng.choice(len(vertices), count, replace=False)
        size = rng.uniform(*spike_magnitude, count) * rng.choice([-1.0, 1.0], count)
        noisy[chosen] += normals[chosen] * size[:, None]
    return noisy


def random_rotation(rng: np.random.Generator) -> FloatArray:
    """A uniformly distributed proper rotation matrix."""
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q *= np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def random_pose(
    points: FloatArray, normals: FloatArray, rng: np.random.Generator, max_offset: float = 200.0
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Rotate and translate points and normals; returns them plus the rotation and offset."""
    rotation = random_rotation(rng)
    offset = rng.uniform(-max_offset, max_offset, 3)
    return points @ rotation.T + offset, normals @ rotation.T, rotation, offset
