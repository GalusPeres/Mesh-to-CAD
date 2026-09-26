"""Design-intent snapping of fitted primitives.

After the free (or user-constrained) fit, candidate design values are tried in
a fixed order: the direction first (plane normal or axis parallel to a global
axis X, Y or Z of the aligned part), then the scalar values (plane offset from
the origin once the normal is axis-parallel, radii, half angle). Values come
from `snapping.snap_length` / `snapping.snap_angle` with the parameter's
standard uncertainty and the project's snap units. Every candidate is tested
with a constrained refit and kept only if it raises the RMS by at most 5 % over
the unsnapped fit. Snaps the user removed (`rejected`) are never tried again.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from m2c_kernel.fitting.constrained import (
    ConstrainedFit,
    Constraints,
    direction_of,
    refine_constrained,
)
from m2c_kernel.fitting.fit import FitError
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import FloatArray
from m2c_kernel.snapping import SnapUnits, snap_angle, snap_length

type SnapId = Literal["direction", "offset", "radius", "halfAngle", "majorRadius", "minorRadius"]
type SnapKind = Literal["direction", "length", "angle"]

MAX_RMS_INCREASE = 0.05
DIRECTION_FLOOR_DEG = 1.0
"""Directions within this angle of a global axis are always tried (the RMS rule decides)."""

GLOBAL_AXES: dict[str, FloatArray] = {
    "X": np.array([1.0, 0.0, 0.0]),
    "Y": np.array([0.0, 1.0, 0.0]),
    "Z": np.array([0.0, 0.0, 1.0]),
}


@dataclass(frozen=True)
class AppliedSnap:
    """A snap that was kept. For directions, `value` and `measured` are angles to the target in degrees."""

    id: SnapId
    kind: SnapKind
    value: float
    measured: float
    uncertainty: float
    target: str | None = None


@dataclass(frozen=True)
class SnapOutcome:
    fit: ConstrainedFit
    constraints: Constraints
    snaps: list[AppliedSnap]


def _value(primitive: Primitive, name: SnapId) -> float | None:
    match primitive, name:
        case Plane(origin=origin, normal=normal), "offset":
            return float(np.asarray(origin) @ np.asarray(normal))
        case (Sphere(radius=radius) | Cylinder(radius=radius)), "radius":
            return float(radius)
        case Cone(half_angle=half_angle), "halfAngle":
            return float(np.degrees(half_angle))
        case Torus(major_radius=major), "majorRadius":
            return float(major)
        case Torus(minor_radius=minor), "minorRadius":
            return float(minor)
    return None


def _with_value(c: Constraints, name: SnapId, value: float) -> Constraints:
    match name:
        case "offset":
            return replace(c, offset=value)
        case "radius":
            return replace(c, radius=value)
        case "halfAngle":
            return replace(c, half_angle=float(np.radians(value)))
        case "majorRadius":
            return replace(c, major_radius=value)
        case "minorRadius":
            return replace(c, minor_radius=value)
    return c


def _is_fixed(c: Constraints, name: SnapId) -> bool:
    match name:
        case "offset":
            return c.offset is not None or c.point is not None
        case "radius":
            return c.radius is not None
        case "halfAngle":
            return c.half_angle is not None
        case "majorRadius":
            return c.major_radius is not None
        case "minorRadius":
            return c.minor_radius is not None
    return True


def _values_of(primitive: Primitive) -> tuple[SnapId, ...]:
    match primitive:
        case Plane():
            return ("offset",)
        case Sphere() | Cylinder():
            return ("radius",)
        case Cone():
            return ("halfAngle",)
        case Torus():
            return ("majorRadius", "minorRadius")
    return ()


def global_axis_of(direction: FloatArray, max_angle_deg: float = 1e-6) -> str | None:
    """Name of the global axis the direction is parallel to (either sign), if any."""
    for name, axis in GLOBAL_AXES.items():
        cosine = min(abs(float(direction @ axis)), 1.0)
        if np.degrees(np.arccos(cosine)) <= max_angle_deg:
            return name
    return None


def snap_fit(
    base: ConstrainedFit,
    points: FloatArray,
    constraints: Constraints,
    rng: np.random.Generator,
    *,
    units: SnapUnits,
    direction_locked: bool,
    rejected: frozenset[str],
) -> SnapOutcome:
    """Apply direction and value snaps that the data supports (see module docstring)."""
    limit = base.rms * (1.0 + MAX_RMS_INCREASE) + 1e-12
    current, c = base, constraints
    snaps: list[AppliedSnap] = []

    def attempt(candidate: Constraints) -> ConstrainedFit | None:
        try:
            trial = refine_constrained(current.primitive, points, candidate, rng)
        except FitError:
            return None
        return trial if trial.rms <= limit else None

    direction = direction_of(current.primitive)
    if direction is not None and not direction_locked and "direction" not in rejected:
        name, axis = min(GLOBAL_AXES.items(), key=lambda item: -abs(float(direction @ item[1])))
        angle = float(np.degrees(np.arccos(min(abs(float(direction @ axis)), 1.0))))
        uncertainty = base.uncertainty.get("direction", 0.0)
        snap = snap_angle(angle, uncertainty, floor_deg=DIRECTION_FLOOR_DEG, candidates=(0.0,))
        if snap is not None:
            candidate = replace(c, direction=axis, perpendicular_to=None)
            trial = attempt(candidate)
            if trial is not None:
                current, c = trial, candidate
                snaps.append(AppliedSnap("direction", "direction", 0.0, angle, uncertainty, name))

    axis_parallel = (d := direction_of(current.primitive)) is not None and global_axis_of(d) is not None
    for name in _values_of(current.primitive):
        if name in rejected or _is_fixed(c, name):
            continue
        if name == "offset" and not axis_parallel:
            continue
        measured = _value(current.primitive, name)
        if measured is None:
            continue
        uncertainty = base.uncertainty.get(name, 0.0)
        kind: SnapKind = "angle" if name == "halfAngle" else "length"
        if kind == "angle":
            snap = snap_angle(measured, uncertainty)
        else:
            snap = snap_length(abs(measured), uncertainty, units=units)
        if snap is None:
            continue
        value = float(np.copysign(snap.value, measured))
        candidate = _with_value(c, name, value)
        trial = attempt(candidate)
        if trial is not None:
            current, c = trial, candidate
            snaps.append(AppliedSnap(name, kind, value, measured, uncertainty))
    return SnapOutcome(fit=current, constraints=c, snaps=snaps)
