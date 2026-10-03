"""Loft ends at planes: the walls continue straight up to the plane and end in it.

Like Extrude's "Bis Ebene", a loft end that names a plane reaches it, whether the
plane lies beyond the last section or inside the lofted range. Sections past the
plane (or right at it) are left out. From the last section before it, every point
continues along the wall's own direction there until it lies in the plane. That
direction is a line fitted through the point's last few sections: the step from one
section to the next alone carries their scanner noise, and extended by a few steps it
makes the end edge wavy (on a remote control: 13 places along its back edge too tight
for a 0.78 mm fillet). The last section of the loft is then a planar wire in the
plane: the cap is that plane and its edge an iso line of the one wall face.

Cutting a longer loft with the plane instead (a boolean with a half-space) gives the
same shape, but its edge is an approximated intersection curve (degree 8, hundreds of
poles, a parametrisation 50 times faster at one end than the other) on which
Open CASCADE cannot run a fillet.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

CLEARANCE_STEPS = 0.3
"""A section closer to the plane than this share of its step is left out, so the last
two sections of the loft are never nearly coincident."""
MIN_APPROACH = 0.05
"""A wall that meets the plane at less than about 3 degrees (this share of its step
towards the plane) does not reach it."""
DIRECTION_SECTIONS = 4
"""Sections the direction of the wall at the end is fitted through."""
MAX_PIECES = 16
"""Most sections of an extension. Up to this many, they are at most one step apart,
which keeps the smooth loft straight along them."""


@dataclass(frozen=True)
class PlaneEnd:
    """A plane a loft ends at (part coordinates)."""

    origin: FloatArray
    normal: FloatArray

    def outward(self, heading: FloatArray) -> FloatArray:
        """The unit normal on the side the loft leaves through, heading along `heading`."""
        normal = unit(self.normal)
        side = float(normal @ unit(heading))
        if abs(side) < MIN_APPROACH:
            # A plane along the axis: the walls never run into it.
            raise KernelError(ErrorCode.PLANE_NOT_REACHED)
        return normal if side > 0.0 else -normal


@dataclass(frozen=True)
class PlaneReach:
    """How a run of sections, ordered towards a plane, reaches it."""

    kept: int
    """Sections kept from the start of the run."""
    extension: tuple[FloatArray, ...]
    """Sections after them, one step apart at most; the last lies in the plane."""


def reach_plane(sections: Sequence[FloatArray], plane: PlaneEnd, heading: FloatArray) -> PlaneReach:
    """Sections that continue `sections` straight up to `plane`, heading along `heading`."""
    away = plane.outward(heading)
    kept = len(sections)
    while kept >= 2:
        last = sections[kept - 1]
        step = _wall_step(sections[max(0, kept - DIRECTION_SECTIONS) : kept])
        approach = step @ away
        distance = (plane.origin - last) @ away
        if (distance > CLEARANCE_STEPS * np.abs(approach)).all():
            if (approach <= MIN_APPROACH * np.linalg.norm(step, axis=1)).any():
                # Part of the wall runs along the plane or away from it: it never gets there.
                raise KernelError(ErrorCode.PLANE_NOT_REACHED)
            reach = distance / approach
            pieces = min(math.ceil(float(reach.max())), MAX_PIECES)
            extension = tuple(
                last + (index / pieces) * reach[:, None] * step for index in range(1, pieces + 1)
            )
            return PlaneReach(kept, extension)
        kept -= 1
    raise KernelError(ErrorCode.PLANE_CUTS_RANGE)


def _wall_step(run: Sequence[FloatArray]) -> FloatArray:
    """Per point, the mean step from one section to the next: a least-squares line."""
    stacked = np.stack(run)
    index = np.arange(len(run), dtype=np.float64) - (len(run) - 1) / 2.0
    slope: FloatArray = np.tensordot(index, stacked, axes=1) / float(index @ index)
    return slope
