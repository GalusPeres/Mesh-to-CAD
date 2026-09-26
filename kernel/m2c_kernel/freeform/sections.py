"""Planar sections of the scan and their normalisation for lofting.

A section plane is `(p - origin) . axis = height`. Vertices with a signed distance of
zero or more count as above the plane, so every triangle is crossed by either none or
exactly two of its edges; crossing points are keyed by their edge, which chains the
segments into loops without comparing floating-point positions.

Loft sections must be compatible: the same number of points, the same orientation
about the axis and a common start direction, otherwise the loft twists
(`.work/research/algorithms-cad.md` 3.4).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import numpy.typing as npt
from scipy.ndimage import gaussian_filter1d

from m2c_kernel.geometry import FloatArray

type IntArray = npt.NDArray[np.int64]

SECTION_POINTS = 96
"""Points per normalised section; enough for sub-micron interpolation error on scans."""


def section_loops(
    vertices: FloatArray, faces: IntArray, origin: FloatArray, axis: FloatArray, height: float
) -> list[FloatArray]:
    """Closed loops of the section at `height` along `axis`, as (n, 3) point arrays.

    Chains that end at a hole in the scan are dropped; they do not bound an area.
    """
    distance = (vertices - origin) @ axis - height
    above = distance >= 0.0
    corners = above[faces]
    crossed = corners.any(axis=1) & ~corners.all(axis=1)
    rows = faces[crossed]
    if len(rows) == 0:
        return []
    edges = np.stack([rows[:, [0, 1]], rows[:, [1, 2]], rows[:, [2, 0]]], axis=1)
    edge_above = above[edges]
    crossing = edge_above[:, :, 0] != edge_above[:, :, 1]
    # Exactly two crossing edges per crossed triangle.
    pairs = edges[crossing].reshape(-1, 2, 2)
    keys = np.sort(pairs, axis=2)
    a, b = keys[..., 0], keys[..., 1]
    t = distance[a] / (distance[a] - distance[b])
    points = vertices[a] + t[..., None] * (vertices[b] - vertices[a])
    return _chain(keys, points)


def _chain(keys: IntArray, points: FloatArray) -> list[FloatArray]:
    """Join segments that share an edge key into closed loops."""
    count = len(keys)
    edge_ids: dict[tuple[int, int], list[int]] = defaultdict(list)
    for segment in range(count):
        for end in range(2):
            edge_ids[(int(keys[segment, end, 0]), int(keys[segment, end, 1]))].append(segment)
    used = np.zeros(count, dtype=bool)
    loops: list[FloatArray] = []
    for start in range(count):
        if used[start]:
            continue
        used[start] = True
        ordered = [points[start, 0]]
        first_key = (int(keys[start, 0, 0]), int(keys[start, 0, 1]))
        key = (int(keys[start, 1, 0]), int(keys[start, 1, 1]))
        point = points[start, 1]
        closed = False
        while True:
            ordered.append(point)
            if key == first_key:
                closed = True
                break
            following = [item for item in edge_ids[key] if not used[item]]
            if not following:
                break
            segment = following[0]
            used[segment] = True
            end = 0 if (int(keys[segment, 0, 0]), int(keys[segment, 0, 1])) == key else 1
            key = (int(keys[segment, 1 - end, 0]), int(keys[segment, 1 - end, 1]))
            point = points[segment, 1 - end]
        if closed and len(ordered) > 3:
            loops.append(np.asarray(ordered[:-1]))
    return loops


def loop_area(loop: FloatArray, axis: FloatArray) -> float:
    """Signed area of a closed loop, counter-clockwise about `axis` positive."""
    relative = loop - loop.mean(axis=0)
    return 0.5 * float(np.cross(relative, np.roll(relative, -1, axis=0)).sum(axis=0) @ axis)


def largest_loop(loops: list[FloatArray], axis: FloatArray) -> FloatArray | None:
    if not loops:
        return None
    return max(loops, key=lambda loop: abs(loop_area(loop, axis)))


def normalise_section(
    loop: FloatArray,
    axis: FloatArray,
    reference: FloatArray,
    count: int = SECTION_POINTS,
    smoothing: float = 1.0,
) -> FloatArray:
    """Resample a closed loop to `count` evenly spaced points.

    The result runs counter-clockwise about `axis` and starts where the loop crosses
    the half-plane of `reference` seen from its centroid. `smoothing` is the Gaussian
    sigma in loop samples; it removes scanner noise without visibly rounding the section.
    """
    if loop_area(loop, axis) < 0:
        loop = loop[::-1]
    loop = _without_duplicates(loop)
    smoothed = gaussian_filter1d(loop, smoothing, axis=0, mode="wrap") if smoothing > 0 else loop
    closed = np.vstack([smoothed, smoothed[:1]])
    length = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
    centre = smoothed.mean(axis=0)
    side = np.cross(axis, reference)
    angle = np.arctan2((smoothed - centre) @ side, (smoothed - centre) @ reference)
    start = float(length[int(np.argmin(np.abs(angle)))])
    samples = (start + np.linspace(0.0, length[-1], count, endpoint=False)) % length[-1]
    return np.column_stack([np.interp(samples, length, closed[:, k]) for k in range(3)])


def _without_duplicates(loop: FloatArray) -> FloatArray:
    step = np.linalg.norm(loop - np.roll(loop, -1, axis=0), axis=1)
    kept: FloatArray = loop[step > 1e-9]
    return kept


def polyline_distance(points: FloatArray, polyline: FloatArray) -> FloatArray:
    """Distance of points to a closed polyline (brute force; sections are small)."""
    start = polyline
    end = np.roll(polyline, -1, axis=0)
    direction = end - start
    length2 = np.maximum((direction * direction).sum(axis=1), 1e-300)
    relative = points[:, None, :] - start[None, :, :]
    t = np.clip((relative * direction[None]).sum(axis=2) / length2[None], 0.0, 1.0)
    nearest = start[None] + t[..., None] * direction[None]
    result: FloatArray = np.linalg.norm(points[:, None, :] - nearest, axis=2).min(axis=1)
    return result
