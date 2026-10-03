"""Planes and axes that solid features take from constructions or the origin.

Standard planes are named by the two axes they contain; their normal is the
positive third axis (XY: +Z, YZ: +X, XZ: +Y).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Construction
from m2c_kernel.fitting.api import Cone, Cylinder, Plane, Torus
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

STANDARD_PLANE_NORMALS: dict[str, tuple[float, float, float]] = {
    "XY": (0.0, 0.0, 1.0),
    "YZ": (1.0, 0.0, 0.0),
    "XZ": (0.0, 1.0, 0.0),
}
STANDARD_AXES: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}

type ConstructionOf = Callable[[str], Construction]


def reference_plane(
    reference: str, construction_of: ConstructionOf
) -> tuple[FloatArray, FloatArray]:
    """Origin and unit normal of a standard plane or a plane feature."""
    if reference in STANDARD_PLANE_NORMALS:
        return np.zeros(3), np.array(STANDARD_PLANE_NORMALS[reference])
    primitive = construction_of(reference).primitive
    if not isinstance(primitive, Plane):
        raise KernelError(ErrorCode.NOT_A_PLANE, {"feature": reference})
    return np.asarray(primitive.origin, dtype=np.float64), unit(primitive.normal)


def reference_axis(
    reference: str, construction_of: ConstructionOf
) -> tuple[FloatArray, FloatArray]:
    """Point and unit direction of a standard axis or of a feature with an axis."""
    if reference in STANDARD_AXES:
        return np.zeros(3), np.array(STANDARD_AXES[reference])
    construction = construction_of(reference)
    if construction.axis is not None:
        axis = construction.axis
        return np.asarray(axis.point, dtype=np.float64), unit(axis.direction)
    match construction.primitive:
        case Cylinder(origin=origin, axis=direction):
            return np.asarray(origin, dtype=np.float64), unit(direction)
        case Cone(apex=apex, axis=direction):
            return np.asarray(apex, dtype=np.float64), unit(direction)
        case Torus(center=center, axis=direction):
            return np.asarray(center, dtype=np.float64), unit(direction)
    raise KernelError(ErrorCode.AXIS_NOT_FOUND, {"feature": reference})
