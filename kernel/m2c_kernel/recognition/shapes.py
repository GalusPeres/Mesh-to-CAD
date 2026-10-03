"""Template shapes of outlines and their signed distance functions (plane frame, mm).

- circle: centre, radius;
- cut circle: a circle trimmed by a straight line (a button cut by the part's
  outline): centre, radius, the direction of the line's normal pointing out of the
  shape (`angle`) and the line's distance from the centre along it (`cut`, 0 for a
  half circle);
- slot (obround): centre, direction, overall length, width;
- rounded rectangle: centre, direction, width, height, corner radius;
- ring segment (an arm of a ring split by straight gaps, e.g. a direction pad):
  centre, inner and outer radius, the angles of the two gap centre lines, the gap
  width (0 gives radial ends) and the corner radius.

A free profile has no template: it is a chain of lines and arcs (`chain.py`); its
parameters only describe where it is and how large it is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray

type ShapeKind = Literal["circle", "cutCircle", "slot", "roundedRect", "ringSegment", "profile"]
type Template = Literal["circle", "cutCircle", "slot", "roundedRect", "ringSegment"]

TAU = 2.0 * np.pi

PARAMETERS: dict[ShapeKind, tuple[str, ...]] = {
    "circle": ("cx", "cy", "radius"),
    "cutCircle": ("cx", "cy", "radius", "angle", "cut"),
    "slot": ("cx", "cy", "angle", "length", "width"),
    "roundedRect": ("cx", "cy", "angle", "width", "height", "corner"),
    "ringSegment": ("cx", "cy", "inner", "outer", "start", "sweep", "gap", "corner"),
    "profile": ("cx", "cy", "width", "height"),
}

LENGTHS: dict[ShapeKind, tuple[str, ...]] = {
    "circle": ("radius",),
    "cutCircle": ("radius", "cut"),
    "slot": ("length", "width"),
    "roundedRect": ("width", "height", "corner"),
    "ringSegment": ("inner", "outer", "gap", "corner"),
    "profile": (),
}
"""The lengths of each shape (sizes a designer types; positions and angles left out)."""


def rotate(points: FloatArray, cx: float, cy: float, angle: float) -> tuple[FloatArray, FloatArray]:
    """Coordinates of the points in a frame at (cx, cy) turned by `angle`."""
    ca, sa = np.cos(angle), np.sin(angle)
    rx, ry = points[:, 0] - cx, points[:, 1] - cy
    return rx * ca + ry * sa, -rx * sa + ry * ca


def circle_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    cx, cy, radius = np.asarray(params, dtype=np.float64)
    result: FloatArray = np.hypot(points[:, 0] - cx, points[:, 1] - cy) - abs(radius)
    return result


def cut_circle_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    """Signed distance to a circle trimmed by a line (exact up to the two sharp corners)."""
    cx, cy, radius, angle, cut = np.asarray(params, dtype=np.float64)
    along, _ = rotate(points, cx, cy, angle)
    round_part = np.hypot(points[:, 0] - cx, points[:, 1] - cy) - abs(radius)
    result: FloatArray = np.maximum(round_part, along - cut)
    return result


def slot_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    """Signed distance to an obround: a segment of length `length - width`, thickened."""
    cx, cy, angle, length, width = np.asarray(params, dtype=np.float64)
    u, v = rotate(points, cx, cy, angle)
    radius = abs(width) / 2.0
    half = max(abs(length) / 2.0 - radius, 0.0)
    result: FloatArray = np.hypot(u - np.clip(u, -half, half), v) - radius
    return result


def rounded_rect_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    cx, cy, angle, width, height, corner = np.asarray(params, dtype=np.float64)
    u, v = rotate(points, cx, cy, angle)
    hw, hh = abs(width) / 2.0, abs(height) / 2.0
    r = min(abs(corner), hw, hh)
    qx, qy = np.abs(u) - (hw - r), np.abs(v) - (hh - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    result: FloatArray = outside + inside - r
    return result


def ring_segment_distance(params: npt.ArrayLike, points: FloatArray) -> FloatArray:
    """Signed distance to a ring arm with rounded corners.

    The arm lies between the radii `inner` and `outer` and between two straight gaps
    of width `gap` centred on the lines through the centre at `start` and
    `start + sweep` (sweep below a half turn). The sharp arm is eroded by the corner
    radius and grown back by it.
    """
    cx, cy, inner, outer, start, sweep, gap, corner = np.asarray(params, dtype=np.float64)
    inner, outer = sorted((abs(inner), abs(outer)))
    sweep = float(np.clip(abs(sweep), 1e-3, np.pi - 1e-3))
    r = min(abs(corner), (outer - inner) / 2.0)
    half_gap = abs(gap) / 2.0
    dx, dy = points[:, 0] - cx, points[:, 1] - cy
    radius = np.hypot(dx, dy)
    band = np.maximum(inner + r - radius, radius - (outer - r))
    end = start + sweep
    # Distances into the arm from both gap centre lines (inward normals).
    from_start = -dx * np.sin(start) + dy * np.cos(start)
    from_end = dx * np.sin(end) - dy * np.cos(end)
    sides = np.maximum(half_gap + r - from_start, half_gap + r - from_end)
    # Distance to the eroded arm: exact beyond a corner (sides and arcs meet at nearly
    # right angles), then grown back by the corner radius.
    outside = np.hypot(np.maximum(band, 0.0), np.maximum(sides, 0.0))
    inside = np.minimum(np.maximum(band, sides), 0.0)
    result: FloatArray = outside + inside - r
    return result


DISTANCES: dict[Template, Callable[[npt.ArrayLike, FloatArray], FloatArray]] = {
    "circle": circle_distance,
    "cutCircle": cut_circle_distance,
    "slot": slot_distance,
    "roundedRect": rounded_rect_distance,
    "ringSegment": ring_segment_distance,
}
