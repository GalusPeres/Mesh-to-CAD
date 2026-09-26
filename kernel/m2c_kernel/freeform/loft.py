"""Lofts through planar sections of the scan along an axis.

Sections are taken at evenly spaced heights between `start` and `end`, each reduced to
its largest closed loop, normalised (same point count, counter-clockwise about the
axis, common start direction) and interpolated by a periodic B-spline. A smooth
`BRepOffsetAPI_ThruSections` solid through these wires is the loft.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.occ import LoftShape, section_wire, thru_sections
from m2c_kernel.freeform.sections import (
    largest_loop,
    normalise_section,
    polyline_distance,
    section_loops,
)
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit
from m2c_kernel.protocol.errors import KernelError

MIN_LENGTH_MM = 0.01
_DEVIATION_SAMPLES = 400

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


def loft_scan(
    vertices: FloatArray,
    faces: IntArray,
    axis: LoftAxis,
    start: float,
    end: float,
    count: int,
    check_cancelled: Callable[[], None] | None = None,
) -> ScanLoft:
    """Loft through `count` sections between `start` and `end` (mm along the axis)."""
    if end - start < MIN_LENGTH_MM:
        raise KernelError(ErrorCode.INVALID_RANGE, {"start": start, "end": end})
    direction = unit(axis.direction)
    reference, _ = frame_from_axis(direction)
    heights = np.linspace(start, end, count)
    sections: list[FloatArray] = []
    deviations: list[FloatArray] = []
    for height in heights:
        if check_cancelled is not None:
            check_cancelled()
        loop = largest_loop(
            section_loops(vertices, faces, axis.point, direction, height), direction
        )
        if loop is None:
            raise KernelError(ErrorCode.NO_SECTION, {"position": round(float(height), 3)})
        points = normalise_section(loop, direction, reference)
        sections.append(points)
        sample = loop[:: max(1, len(loop) // _DEVIATION_SAMPLES)]
        deviations.append(polyline_distance(sample, points))
    wires = [section_wire(points) for points in sections]
    solid = thru_sections(wires)
    distances = np.concatenate(deviations)
    return ScanLoft(
        solid=solid,
        heights=heights,
        sections=tuple(sections),
        section_rms=float(np.sqrt(np.mean(distances**2))),
        section_max=float(distances.max()),
    )
