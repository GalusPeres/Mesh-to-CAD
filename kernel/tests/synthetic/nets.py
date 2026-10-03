"""Freeform nets with known shape: a band around flared walls, as laid around a remote.

A band is a ring of quads around the z axis over an elliptic, flared wall: open at the
top and the bottom, so planes there close it into a solid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class BandNet:
    vertices: npt.NDArray[np.float64]
    quads: npt.NDArray[np.int64]
    """Counter-clockwise seen from outside (the normals point away from the axis)."""
    around: int
    rows: int


def band_net(
    *,
    around: int = 16,
    rows: int = 4,
    bottom: float = -1.0,
    top: float = 11.0,
    radius_bottom: float = 20.0,
    radius_top: float = 16.0,
    aspect: float = 0.6,
) -> BandNet:
    """A ring of `around` x `rows` quads; the wall narrows from bottom to top.

    Row j of control points lies at height `bottom + (top - bottom) * j / rows`; the
    ellipse has semi-axes r and `aspect` * r, with r going linearly with the height.
    """
    vertices = []
    for j in range(rows + 1):
        height = bottom + (top - bottom) * j / rows
        radius = radius_bottom + (radius_top - radius_bottom) * j / rows
        for i in range(around):
            angle = 2 * np.pi * i / around
            vertices.append((radius * np.cos(angle), aspect * radius * np.sin(angle), height))
    quads = []
    for j in range(rows):
        for i in range(around):
            a, b = j * around + i, j * around + (i + 1) % around
            quads.append((a, b, b + around, a + around))
    return BandNet(np.array(vertices), np.array(quads, dtype=np.int64), around, rows)
