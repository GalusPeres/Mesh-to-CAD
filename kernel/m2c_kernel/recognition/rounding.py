"""The rounding of a recognised feature's top edge, measured from the scan.

A feature is built as a prism: walls straight up from its outline, a flat or inclined
top (for a pocket: its mouth in the plane it is sunk into). Where the wall meets the top, the
scan shows the edge's rounding. Cross-sections along the fitted outline at the top
measure it like `fillet.scanRadius` measures a body edge (`fitting/corner.py`): the
wall runs down from the corner, the top inwards (a pocket's plane outwards).
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from m2c_kernel.fitting.corner import CornerFrame, EdgeRadius, edge_radius
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.recognition.chain import chain_points
from m2c_kernel.recognition.contours import signed_area
from m2c_kernel.recognition.outline import Outline
from m2c_kernel.recognition.planes import BasePlane
from m2c_kernel.recognition.relief import Relief

SECTIONS = 24
MAX_SHARE = 0.9
"""A rounding takes at most this share of the wall's height and of half the width."""


def top_rounding(
    vertices: FloatArray,
    tree: cKDTree,
    plane: BasePlane,
    relief: Relief,
    noise: float,
) -> EdgeRadius | None:
    """The rounding of the feature's top edge (a pocket's mouth); None if not measured."""
    if relief.top == "through" and relief.kind == "boss":
        return None
    frames = outline_frames(plane, relief)
    limit = MAX_SHARE * min(relief.height, _half_width(relief.outline))
    if not frames or limit <= 0.0:
        return None
    return edge_radius(vertices, tree, frames, noise, max_radius=limit)


def outline_frames(plane: BasePlane, relief: Relief, count: int = SECTIONS) -> list[CornerFrame]:
    """Cross-sections spread evenly along the outline, at the top (a pocket's mouth)."""
    ring = chain_points(relief.outline.chain)
    if len(ring) < 3:
        return []
    if signed_area(ring) < 0.0:
        ring = ring[::-1]
    closed = np.vstack([ring, ring[:1]])
    steps = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    length = np.concatenate([[0.0], np.cumsum(steps)])
    at = (np.arange(count) + 0.5) * length[-1] / count
    points = np.column_stack(
        [np.interp(at, length, closed[:, 0]), np.interp(at, length, closed[:, 1])]
    )
    segment = np.clip(np.searchsorted(length, at, side="right") - 1, 0, len(steps) - 1)
    tangents = unit(closed[segment + 1] - closed[segment])
    # Counter-clockwise ring: the outward normal is the tangent turned clockwise.
    outward = np.column_stack([tangents[:, 1], -tangents[:, 0]])
    boss = relief.kind == "boss"
    heights = relief.top_at(points) if boss else np.full(count, relief.level)
    corners = plane.from_plane(np.column_stack([points, heights]))
    # The top runs inwards along its own (possibly inclined) plane.
    rise = np.array(relief.slope) if boss else np.zeros(2)
    frame_axes = np.column_stack([plane.x_axis, plane.y_axis, plane.normal])
    down = -plane.normal
    frames = []
    for corner, tangent, out in zip(corners, tangents, outward, strict=True):
        across = -out if boss else out
        frames.append(
            CornerFrame(
                point=corner,
                tangent=unit(frame_axes @ np.append(tangent, tangent @ rise)),
                faces=(down, unit(frame_axes @ np.append(across, across @ rise))),
            )
        )
    return frames


def _half_width(outline: Outline) -> float:
    """Half the narrowest width of the outline: the largest rounding that fits on top."""
    values = outline.named()
    match outline.kind:
        case "circle" | "cutCircle":
            return float(values["radius"])
        case "slot":
            return float(values["width"]) / 2.0
        case "ringSegment":
            return float(values["outer"] - values["inner"]) / 2.0
        case _:
            return float(min(values["width"], values["height"])) / 2.0
