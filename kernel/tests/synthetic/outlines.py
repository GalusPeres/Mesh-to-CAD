"""Contours of template shapes with noise, for the outline fits.

Points are found on the zero set of the template's distance function (the shape the
fit measures against), by bisection along rays from a point inside the shape.
"""

from __future__ import annotations

import numpy as np

from m2c_kernel.recognition.outline import Outline
from m2c_kernel.recognition.shapes import DISTANCES

TAU = 2.0 * np.pi


def template_contour(outline: Outline, count: int, noise: float, seed: int) -> np.ndarray:
    """`count` points around the template's boundary with Gaussian noise of `noise` mm."""
    kind = outline.kind
    assert kind != "profile"
    distance = DISTANCES[kind]
    p = outline.named()
    cx, cy = outline.center
    if kind == "ringSegment":
        # The ring's centre lies outside the arm: start from the middle of the arm.
        middle = p["start"] + p["sweep"] / 2.0
        cx += (p["inner"] + p["outer"]) / 2.0 * np.cos(middle)
        cy += (p["inner"] + p["outer"]) / 2.0 * np.sin(middle)
    if kind == "cutCircle":
        # Halfway between the cut and the far side of the circle.
        middle = (p["cut"] - p["radius"]) / 2.0
        cx += middle * np.cos(p["angle"])
        cy += middle * np.sin(p["angle"])
    reach = 4.0 * max(abs(value) for value in outline.params[2:]) + 1.0
    angles = np.linspace(0.0, TAU, count, endpoint=False)
    rays = np.column_stack([np.cos(angles), np.sin(angles)])
    low, high = np.zeros(count), np.full(count, reach)
    for _ in range(40):
        mid = (low + high) / 2.0
        along = np.column_stack([cx + rays[:, 0] * mid, cy + rays[:, 1] * mid])
        inside = distance(outline.params, along) < 0
        low = np.where(inside, mid, low)
        high = np.where(inside, high, mid)
    points = np.column_stack([cx + rays[:, 0] * low, cy + rays[:, 1] * low])
    result: np.ndarray = points + np.random.default_rng(seed).normal(0.0, noise, points.shape)
    return result
