"""Loft ends at planes: the walls continue straight past the plane and are cut there.

Like Extrude's "Bis Ebene", a loft end that names a plane reaches it, whether the
plane lies beyond the last section or inside the lofted range. Beyond it, an extra
section continues every point of the last section along its step from the section
before (the wall's own direction there) until all of it lies a little past the plane.
The smooth loft through it keeps one wall face from end to end, so a fillet on the
end edge rolls along a single face. The loft feature then cuts the solid at the plane.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

PAST_PLANE_MM = 1.0
"""The extra section lies at least this far past the plane, so the cut is clean."""
_MIN_APPROACH = 1e-6
"""A wall point closer to the plane by less than this per step does not reach it."""


@dataclass(frozen=True)
class PlaneEnd:
    """A plane a loft ends at (part coordinates)."""

    origin: FloatArray
    normal: FloatArray

    def kept_side(self, inside: FloatArray) -> FloatArray:
        """The unit normal pointing to the side of the plane that holds `inside`."""
        normal = unit(self.normal)
        return normal if float((inside - self.origin) @ normal) >= 0.0 else -normal


def past_plane(
    section: FloatArray, previous: FloatArray, plane: PlaneEnd, inside: FloatArray
) -> FloatArray | None:
    """A section beyond `plane`, continuing the step from `previous` to `section`.

    None when `section` already lies past the plane (the cut alone ends the loft).
    """
    away = -plane.kept_side(inside)
    beyond = (section - plane.origin) @ away
    short = beyond < PAST_PLANE_MM
    if not short.any():
        return None
    step = section - previous
    approach = step @ away
    if (approach[short] <= _MIN_APPROACH).any():
        # Part of the wall runs along the plane or away from it: it never gets there.
        raise KernelError(ErrorCode.PLANE_NOT_REACHED)
    factor = float(np.max((PAST_PLANE_MM - beyond[short]) / approach[short]))
    result: FloatArray = section + factor * step
    return result
