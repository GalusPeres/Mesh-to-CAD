"""The chain of lines and arcs of every template shape (`shapes.py`), in the plane frame.

The chains run counter-clockwise. Neighbouring lines and arcs of rounded shapes are
tangent; a slot's sides are parallel and its ends of equal radius; a cut circle
keeps sharp corners where the cut meets the circle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.chain import Chain, Edge, Relation, point
from m2c_kernel.recognition.shapes import Template

MIN_CORNER_MM = 0.01
"""Smaller corner radii are left sharp."""

type ArcSpec = tuple[FloatArray, float, bool] | None
"""Centre, radius and direction of an arc, or None for a line."""


def template_chain(kind: Template, p: dict[str, float]) -> Chain:
    match kind:
        case "circle":
            centre = np.array([p["cx"], p["cy"]])
            on = point(centre + np.array([p["radius"], 0.0]))
            return Chain((Edge(on, on, point(centre), p["radius"]),))
        case "cutCircle":
            return _cut_circle(p)
        case "slot":
            return _slot(p)
        case "roundedRect":
            return _rounded_rect(p)
        case "ringSegment":
            return _ring_segment(p)


def _unit(angle: float) -> FloatArray:
    return np.array([np.cos(angle), np.sin(angle)])


def _ccw(centre: FloatArray, start: FloatArray, end: FloatArray) -> bool:
    """Direction of the shorter arc from start to end around the centre."""
    a, b = start - centre, end - centre
    return bool(a[0] * b[1] - a[1] * b[0] > 0.0)


def _closed(
    corners: Sequence[FloatArray],
    arcs: Sequence[ArcSpec],
    extra: Sequence[Relation] = (),
    *,
    smooth: bool = True,
) -> Chain:
    """Corner i to corner i + 1, straight or along arc i.

    With `smooth`, neighbouring lines and arcs are tangent; else the corners are sharp.
    """
    edges: list[Edge] = []
    for i, arc in enumerate(arcs):
        start, end = point(corners[i]), point(corners[(i + 1) % len(corners)])
        if arc is None:
            edges.append(Edge(start, end))
        else:
            centre, radius, ccw = arc
            edges.append(Edge(start, end, point(centre), float(radius), ccw))
    relations: list[Relation] = [
        ("tangent", (i, (i + 1) % len(arcs)))
        for i in range(len(arcs))
        if smooth and (arcs[i] is None) != (arcs[(i + 1) % len(arcs)] is None)
    ]
    return Chain(tuple(edges), (*relations, *extra))


def _cut_circle(p: dict[str, float]) -> Chain:
    """The arc around the far side of the centre, then back along the cut."""
    centre = np.array([p["cx"], p["cy"]])
    normal, along = _unit(p["angle"]), _unit(p["angle"] + np.pi / 2.0)
    radius = p["radius"]
    cut = float(np.clip(p["cut"], -radius + 1e-3, radius - 1e-3))
    half = np.sqrt(radius**2 - cut**2)
    first = centre + cut * normal + half * along
    last = centre + cut * normal - half * along
    return _closed([first, last], [(centre, radius, True), None], smooth=False)


def _slot(p: dict[str, float]) -> Chain:
    centre = np.array([p["cx"], p["cy"]])
    along, across = _unit(p["angle"]), _unit(p["angle"] + np.pi / 2.0)
    radius = p["width"] / 2.0
    half = max(p["length"] / 2.0 - radius, 1e-3)
    right, left = centre + half * along, centre - half * along
    corners = [
        right + radius * across,
        left + radius * across,
        left - radius * across,
        right - radius * across,
    ]
    arcs: list[ArcSpec] = [None, (left, radius, True), None, (right, radius, True)]
    return _closed(corners, arcs, [("parallel", (0, 2)), ("equalRadius", (1, 3))])


def _rounded_rect(p: dict[str, float]) -> Chain:
    """Counter-clockwise from the end of the bottom side: corner arcs and sides."""
    centre = np.array([p["cx"], p["cy"]])
    x, y = _unit(p["angle"]), _unit(p["angle"] + np.pi / 2.0)
    hw, hh = p["width"] / 2.0, p["height"] / 2.0
    r = min(p["corner"], hw, hh)
    if r < MIN_CORNER_MM:
        sharp = [
            centre + sx * hw * x + sy * hh * y for sx, sy in ((1, -1), (1, 1), (-1, 1), (-1, -1))
        ]
        return _closed(sharp, [None] * 4)
    corners: list[FloatArray] = []
    arcs: list[ArcSpec] = []
    # Corner centres bottom right, top right, top left, bottom left; each arc runs from
    # the side before the corner to the side after it.
    for sx, sy, before, after in (
        (1, -1, -y, x),
        (1, 1, x, y),
        (-1, 1, y, -x),
        (-1, -1, -x, -y),
    ):
        corner = centre + sx * (hw - r) * x + sy * (hh - r) * y
        corners += [corner + r * before, corner + r * after]
        arcs += [(corner, r, True), None]
    return _closed(corners, arcs)


def _ring_segment(p: dict[str, float]) -> Chain:
    """A ring arm: outer and inner arc, two straight gap sides, rounded corners.

    Counter-clockwise: out along the start side, the outer arc to the end side, in
    along the end side, the inner arc back. A corner fillet of radius r is tangent to
    the gap side (its centre r from the side) and to the circle (its centre r inside
    the outer circle, r outside the inner one).
    """
    centre = np.array([p["cx"], p["cy"]])
    inner, outer = p["inner"], p["outer"]
    start, end = p["start"], p["start"] + p["sweep"]
    half_gap = p["gap"] / 2.0
    r = min(p["corner"], (outer - inner) / 2.0 - 1e-3)
    # Gap centre lines and their normals pointing into the arm.
    sides = ((_unit(start), _unit(start + np.pi / 2.0)), (_unit(end), _unit(end - np.pi / 2.0)))

    def at(side: int, radius: float, inset: float) -> FloatArray:
        """Point `inset` from the gap centre line and `radius` from the ring centre."""
        d, n = sides[side]
        t = np.sqrt(max(radius**2 - inset**2, 0.0))
        result: FloatArray = centre + t * d + inset * n
        return result

    if r < MIN_CORNER_MM:
        corners = [
            at(0, outer, half_gap),
            at(1, outer, half_gap),
            at(1, inner, half_gap),
            at(0, inner, half_gap),
        ]
        sharp: list[ArcSpec] = [(centre, outer, True), None, (centre, inner, False), None]
        return _closed(corners, sharp, smooth=False)

    def fillet(side: int, radius: float, outside: bool) -> tuple[Any, FloatArray, FloatArray]:
        """Centre, tangent point on the gap side, tangent point on the circle."""
        _, n = sides[side]
        middle = at(side, radius - r if outside else radius + r, half_gap + r)
        on_side = middle - r * n
        towards = (middle - centre) / np.linalg.norm(middle - centre)
        on_circle = centre + radius * towards
        return middle, on_side, on_circle

    c1, s1, o1 = fillet(0, outer, True)
    c2, s2, o2 = fillet(1, outer, True)
    c3, s3, i3 = fillet(1, inner, False)
    c4, s4, i4 = fillet(0, inner, False)
    corners = [s1, o1, o2, s2, s3, i3, i4, s4]
    arcs: list[ArcSpec] = [
        (c1, r, _ccw(c1, s1, o1)),
        (centre, outer, True),
        (c2, r, _ccw(c2, o2, s2)),
        None,
        (c3, r, _ccw(c3, s3, i3)),
        (centre, inner, False),
        (c4, r, _ccw(c4, i4, s4)),
        None,
    ]
    return _closed(corners, arcs)
