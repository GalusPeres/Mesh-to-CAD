"""Compatible loft sections: every corner at the same point index in every section.

Sections resampled each on its own by arc length put a corner on a different point in
each section: on the remote control up to 13 points (5.7 mm along the outline) over 12
sections. The loft then runs diagonally across the corner between two sections and
dents it at every section line.

Here the corners of a reference outline are found (peaks of the turning over
WINDOW_MM); with the start of the outline they are the anchors. Every section puts each
anchor on its own nearest corner (or, without one nearby, its nearest point). Between
two anchors every section gets the same number of points, set by the reference and
evenly spaced along the section's own stretch, so a corner and the points around it
correspond from section to section. The reference is the scan's section in the middle
of its extent, not one of the loft's, so a section gets the same points in every loft
through it and two lofts that meet there unite.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from m2c_kernel.freeform.sections import Outline
from m2c_kernel.geometry import FloatArray

STEP_MM = 0.05
"""Spacing of the fine samples corners are searched on."""
WINDOW_MM = 1.0
"""The turning at a point is measured between the directions this far before and after."""
CORNER_DEG = 40.0
"""Turning that makes a corner: a radius below about 2.9 mm."""
REGION_DEG = 20.0
"""A corner spans the stretch around its peak where the turning stays above this, so
noise on a curve near CORNER_DEG does not split it into several corners."""
MATCH_MM = 3.0
"""Farthest a corner may lie beside the matching corner of the section before."""
MIN_GAP_MM = 1.0
"""Anchors closer than this along the outline are merged."""


def anchored_sections(
    outlines: Sequence[Outline], reference: Outline, axis: FloatArray, count: int
) -> list[FloatArray]:
    """`count` points per outline, with the reference's corners on the same points."""
    anchors = _own_anchors(reference, axis)
    counts = _stretch_counts(anchors, reference.total, count)
    return [
        _resample(shape, _matched(shape, reference, anchors, axis), counts) for shape in outlines
    ]


def corners(shape: Outline, axis: FloatArray) -> FloatArray:
    """Arc lengths of the corners of an outline, ascending."""
    arcs = np.arange(0.0, shape.total, STEP_MM)
    points = shape.at(arcs)
    tangents = np.roll(points, -1, axis=0) - points
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-12)
    window = max(1, round(WINDOW_MM / STEP_MM))
    before, after = np.roll(tangents, window, axis=0), np.roll(tangents, -window, axis=0)
    turning = np.degrees(
        np.abs(np.arctan2(np.cross(before, after) @ axis, np.einsum("ij,ij->i", before, after)))
    )
    sharp = turning > REGION_DEG
    if turning.max() <= CORNER_DEG or sharp.all():
        return np.empty(0)
    # Runs of sharp samples, rolled so that no run wraps around the start.
    shift = int(np.argmin(sharp))
    rolled_sharp, rolled_turning = np.roll(sharp, -shift), np.roll(turning, -shift)
    # A sharp run at the very end still ends: pad with one sample that is not sharp.
    edges = np.flatnonzero(np.diff(np.append(rolled_sharp, False).astype(np.int8)))
    found = []
    for begin, end in zip(edges[::2] + 1, edges[1::2] + 1, strict=True):
        index = np.arange(begin, end)
        weights = rolled_turning[index]
        if weights.max() <= CORNER_DEG:
            continue
        centre = float((index * weights).sum() / weights.sum())
        found.append(((centre + shift) * STEP_MM) % shape.total)
    return np.sort(np.asarray(found))


def _own_anchors(shape: Outline, axis: FloatArray) -> FloatArray:
    """The start and the corners of an outline, merged where they lie too close."""
    arcs = [0.0]
    for arc in corners(shape, axis):
        if arc - arcs[-1] >= MIN_GAP_MM and shape.total - arc >= MIN_GAP_MM:
            arcs.append(float(arc))
    return np.asarray(arcs)


def _matched(
    shape: Outline, reference: Outline, anchors: FloatArray, axis: FloatArray
) -> FloatArray:
    """The anchors of `reference` on `shape`: its nearest corner, else its nearest point."""
    targets = _flat(reference.at(anchors), axis)
    candidates = corners(shape, axis)
    candidate_points = _flat(shape.at(candidates), axis) if len(candidates) else None
    fine = np.arange(0.0, shape.total, STEP_MM)
    fine_points = _flat(shape.at(fine), axis)
    result = [0.0]
    for target in targets[1:]:
        arc = None
        if candidate_points is not None:
            distances = np.linalg.norm(candidate_points - target, axis=1)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= MATCH_MM:
                arc = float(candidates[nearest])
        if arc is None:
            arc = float(fine[int(np.argmin(np.linalg.norm(fine_points - target, axis=1)))])
        result.append(arc)
    return _ascending(np.asarray(result), shape.total)


def _ascending(arcs: FloatArray, total: float) -> FloatArray:
    """Anchors in order along the outline; one out of order moves between its neighbours."""
    fixed = arcs.copy()
    for index in range(1, len(fixed)):
        upper = fixed[index + 1] if index + 1 < len(fixed) else total
        if not fixed[index - 1] < fixed[index] < upper:
            following = upper if upper > fixed[index - 1] else total
            fixed[index] = (fixed[index - 1] + following) / 2.0
    return fixed


def _flat(points: FloatArray, axis: FloatArray) -> FloatArray:
    """Points moved along the axis onto the plane through the origin."""
    result: FloatArray = points - np.outer(points @ axis, axis)
    return result


def _stretch_counts(anchors: FloatArray, total: float, count: int) -> list[int]:
    """Points per stretch between anchors: where the anchors fall among `count` even steps."""
    starts = np.round(np.append(anchors, total) / total * count).astype(int)
    return [max(1, int(value)) for value in np.diff(np.maximum.accumulate(starts))]


def _resample(shape: Outline, anchors: FloatArray, counts: list[int]) -> FloatArray:
    ends = np.append(anchors, shape.total)
    arcs = np.concatenate(
        [
            ends[index] + (ends[index + 1] - ends[index]) * np.arange(number) / number
            for index, number in enumerate(counts)
        ]
    )
    return shape.at(arcs)
