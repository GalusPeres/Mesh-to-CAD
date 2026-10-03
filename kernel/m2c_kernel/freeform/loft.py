"""Lofts through planar sections of the scan along an axis.

Sections are taken at evenly spaced heights between `start` and `end`, each reduced to
its largest closed loop, normalised (same point count, counter-clockwise about the
axis, common start direction) and interpolated by a periodic B-spline. A smooth
`BRepOffsetAPI_ThruSections` solid through these wires is the loft.

A loft follows walls that run along the axis. Where a section grows or shrinks sideways
much faster than it moves along the axis, the range has run into something else: a
button on a remote's top, or a flat slope at its bottom. A smooth loft through such a
section swings far outside the scan (on the remote: 19 times the volume) and can take
minutes to build. `body_range` finds the stretch where the walls stay steep;
`loft_scan` refuses a section beyond it. Up to a plane the walls continue straight
instead (`ends.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.anchors import anchored_sections
from m2c_kernel.freeform.ends import PlaneEnd, reach_plane
from m2c_kernel.freeform.occ import LoftShape, section_wire, thru_sections
from m2c_kernel.freeform.sections import (
    SECTION_POINTS,
    Outline,
    largest_loop,
    loop_area,
    outline,
    polyline_distance,
    section_loops,
)
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit
from m2c_kernel.protocol.errors import KernelError

MIN_LENGTH_MM = 0.01
_DEVIATION_SAMPLES = 400
MAX_WALL_SLOPE = 2.0
"""How far a section may lie beside its neighbour, per mm along the axis, anywhere around
it, for a loft to follow (a wall at least about 27 degrees from the section plane)."""
_SLOPE_SAMPLES = 200
"""Points of one section compared with the outline of the next."""
_SLOPE_OUTLINE = 600
"""Most points of the outline they are compared with."""
_HOLE_NUDGES_MM = (0.05, -0.05, 0.15, -0.15, 0.3, -0.3)
"""Where a section meets a small hole in the scan and does not close, the plane moves
this far and tries again; the loop keeps its real height, so the loft stays exact."""
RANGE_SAMPLES = 40
"""Sections that `body_range` looks at between the ends of the scan."""
SECTION_SPACING_MM = 0.5
"""Spacing of the points of a normalised section. Coarser sections cut the corners of
the outline: with 96 points around a remote control (3.4 mm apart) the sections were
0.09 mm off on average and 1.1 mm at the corners, with 768 points 0.004 and 0.13 mm."""
MAX_SECTION_POINTS = SECTION_POINTS * 16

type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class LoftAxis:
    point: FloatArray
    direction: FloatArray


@dataclass(frozen=True)
class ScanLoft:
    solid: LoftShape
    heights: FloatArray
    sections: tuple[FloatArray, ...]
    """Normalised section points, one (n, 3) array per height."""
    section_rms: float
    section_max: float
    """Distance of the raw section points to the normalised sections."""


def scan_extent(vertices: FloatArray, axis: LoftAxis) -> tuple[float, float]:
    """Lowest and highest coordinate of the scan along the axis."""
    heights = (vertices - axis.point) @ unit(axis.direction)
    return float(heights.min()), float(heights.max())


@dataclass(frozen=True)
class _Section:
    loop: FloatArray | None
    """The largest closed loop, or None where the scan gives none."""
    flat: FloatArray | None
    """The loop moved along the axis onto the plane through the axis point."""
    area: float


def _section(
    vertices: FloatArray, faces: IntArray, axis: LoftAxis, direction: FloatArray, height: float
) -> _Section:
    loop = None
    for nudge in (0.0, *_HOLE_NUDGES_MM):
        loops = section_loops(vertices, faces, axis.point, direction, height + nudge)
        loop = largest_loop(loops, direction)
        if loop is not None:
            break
    if loop is None:
        return _Section(None, None, 0.0)
    flat = loop - np.outer((loop - axis.point) @ direction, direction)
    return _Section(loop, flat, abs(loop_area(loop, direction)))


def _thinned(loop: FloatArray, count: int) -> FloatArray:
    return loop[:: max(1, len(loop) // count)]


def _continues(a: _Section, b: _Section, step: float) -> bool:
    """Whether `b`, `step` mm along the axis from `a`, belongs to the same lofted body.

    No point of either section may lie further beside the other than the walls allow.
    """
    if a.flat is None or b.flat is None:
        return False
    beside = max(
        float(
            polyline_distance(
                _thinned(b.flat, _SLOPE_SAMPLES), _thinned(a.flat, _SLOPE_OUTLINE)
            ).max()
        ),
        float(
            polyline_distance(
                _thinned(a.flat, _SLOPE_SAMPLES), _thinned(b.flat, _SLOPE_OUTLINE)
            ).max()
        ),
    )
    return beside <= MAX_WALL_SLOPE * abs(step)


def body_range(
    vertices: FloatArray,
    faces: IntArray,
    axis: LoftAxis,
    low: float,
    high: float,
    samples: int = RANGE_SAMPLES,
) -> tuple[float, float]:
    """Where between `low` and `high` the sections form one body to loft through.

    It starts at the largest section and grows both ways as long as the next section
    continues the walls (`MAX_WALL_SLOPE`). The outermost sections of that stretch may
    still touch the slope or rounding beyond it, so the ends lie half a sample step
    further inside.
    """
    direction = unit(axis.direction)
    step = (high - low) / samples
    heights = low + step * (np.arange(samples) + 0.5)
    sections = [_section(vertices, faces, axis, direction, float(h)) for h in heights]
    peak = int(np.argmax([section.area for section in sections]))
    if sections[peak].loop is None:
        return low, high
    first = last = peak
    while first > 0 and _continues(sections[first], sections[first - 1], step):
        first -= 1
    while last < samples - 1 and _continues(sections[last], sections[last + 1], step):
        last += 1
    if first == last:
        return float(heights[first]), float(heights[last])
    return float(heights[first] + step / 2), float(heights[last] - step / 2)


def section_points(vertices: FloatArray, faces: IntArray, direction: FloatArray) -> int:
    """Points per normalised section: SECTION_SPACING_MM around the scan's outline.

    The outline is estimated from the scan's extent across the axis, not from the
    sections, so every loft along the same axis gets the same count: a loft that
    continues another one through the same section then meets it in the same wire
    (with different counts the two caps differ slightly and their union fails). The
    count is 96 times a power of two.
    """
    used = vertices[np.unique(faces)]
    across, other = frame_from_axis(direction)
    width, height = np.ptp(used @ across), np.ptp(used @ other)
    count = SECTION_POINTS
    while count < MAX_SECTION_POINTS and count * SECTION_SPACING_MM < 2.0 * (width + height):
        count *= 2
    return count


def _reference_outline(
    vertices: FloatArray, faces: IntArray, axis: LoftAxis, outlines: list[Outline]
) -> Outline:
    """The section in the middle of the scan's extent, the same for every loft along `axis`.

    Its corners anchor the points of all sections (`anchors.py`). Where the scan has no
    closed section there, the loft's middle section stands in.
    """
    direction = unit(axis.direction)
    low, high = scan_extent(vertices[np.unique(faces)], axis)
    section = _section(vertices, faces, axis, direction, (low + high) / 2.0)
    if section.loop is None:
        return outlines[len(outlines) // 2]
    reference, _ = frame_from_axis(direction)
    return outline(section.loop, direction, reference)


def loft_scan(
    vertices: FloatArray,
    faces: IntArray,
    axis: LoftAxis,
    start: float,
    end: float,
    count: int,
    check_cancelled: Callable[[], None] | None = None,
    start_plane: PlaneEnd | None = None,
    end_plane: PlaneEnd | None = None,
) -> ScanLoft:
    """Loft through `count` sections between `start` and `end` (mm along the axis).

    An end with a plane continues straight up to it and ends in it (`ends.py`).
    """
    if end - start < MIN_LENGTH_MM:
        raise KernelError(ErrorCode.INVALID_RANGE, {"start": start, "end": end})
    direction = unit(axis.direction)
    reference, _ = frame_from_axis(direction)
    heights = np.linspace(start, end, count)
    loops: list[FloatArray] = []
    previous: _Section | None = None
    for height in heights:
        if check_cancelled is not None:
            check_cancelled()
        section = _section(vertices, faces, axis, direction, float(height))
        loop = section.loop
        if loop is None:
            raise KernelError(ErrorCode.NO_SECTION, {"position": round(float(height), 3)})
        if previous is not None and not _continues(previous, section, heights[1] - heights[0]):
            raise KernelError(ErrorCode.SECTION_JUMP, {"position": round(float(height), 3)})
        previous = section
        loops.append(loop)
    outlines = [outline(loop, direction, reference) for loop in loops]
    sections = anchored_sections(
        outlines,
        _reference_outline(vertices, faces, axis, outlines),
        direction,
        section_points(vertices, faces, direction),
    )
    deviations = [
        polyline_distance(loop[:: max(1, len(loop) // _DEVIATION_SAMPLES)], points)
        for loop, points in zip(loops, sections, strict=True)
    ]
    first, last = 0, len(sections)
    before: tuple[FloatArray, ...] = ()
    after: tuple[FloatArray, ...] = ()
    if end_plane is not None:
        reach = reach_plane(sections, end_plane, direction)
        last, after = reach.kept, reach.extension
    if start_plane is not None:
        reach = reach_plane(sections[last - 1 :: -1], start_plane, -direction)
        first, before = last - reach.kept, reach.extension[::-1]
    sections, deviations = sections[first:last], deviations[first:last]
    solid = thru_sections([section_wire(points) for points in (*before, *sections, *after)])
    distances = np.concatenate(deviations)
    return ScanLoft(
        solid=solid,
        heights=heights[first:last],
        sections=tuple(sections),
        section_rms=float(np.sqrt(np.mean(distances**2))),
        section_max=float(distances.max()),
    )
