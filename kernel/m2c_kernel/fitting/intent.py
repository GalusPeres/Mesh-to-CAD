"""Design-intent snapping of fitted primitives and clustering of feature directions.

After the free (or user-constrained) fit, design values are tried in a fixed
order: the direction first (plane normal or axis parallel or perpendicular to
the X, Y or Z axis of the part), then the scalar values (plane offset from the
origin once the normal is axis-parallel, radii, half angle). Candidate values
come from `snapping.snap_length` / `snapping.snap_angle` with the uncertainty
of the parameter in the current fit and the project's snap units. Every
candidate is tested with a constrained refit and kept only if the RMS stays
within 5 % of the unsnapped fit. Snaps the user removed are never tried again.

Direction windows are at least one degree wide: after alignment, features of a
real part scatter by a few hundredths of a degree around the design axes, more
than the statistical uncertainty of a single fit. The RMS test rejects a
genuinely tilted feature (research notes, algorithms-mesh.md 4.1 and 4.4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.constrained import (
    ConstrainedFit,
    Constraints,
    direction_of,
    refine_constrained,
)
from m2c_kernel.fitting.fit import FitError
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.snapping import SnapUnits, snap_angle, snap_length

type SnapId = Literal["direction", "offset", "radius", "halfAngle", "majorRadius", "minorRadius"]
type SnapKind = Literal["direction", "length", "angle"]
type AxisName = Literal["X", "Y", "Z"]

MAX_RMS_INCREASE = 0.05
"""A snap is kept only if the RMS rises by at most this share over the unsnapped fit."""

DIRECTION_WINDOW_DEG = 1.0

CONE_HALF_ANGLES_DEG: tuple[float, ...] = (15.0, 22.5, 30.0, 41.0, 45.0, 50.0, 59.0, 60.0, 75.0)
"""Half angles of common cones: chamfers, countersinks (82, 90, 100 deg), drill points (118)."""

GLOBAL_AXES: dict[AxisName, FloatArray] = {
    "X": np.array([1.0, 0.0, 0.0]),
    "Y": np.array([0.0, 1.0, 0.0]),
    "Z": np.array([0.0, 0.0, 1.0]),
}

SNAP_ORDER: tuple[SnapId, ...] = (
    "direction",
    "offset",
    "radius",
    "halfAngle",
    "majorRadius",
    "minorRadius",
)


@dataclass(frozen=True, kw_only=True)
class AppliedSnap:
    """A design value the fit was constrained to, with the measurement it replaced.

    Lengths are in mm, angles in degrees. For `direction`, `value` is the design
    angle to the axis `target` (0 = parallel, 90 = perpendicular) and `measured`
    the measured angle; `uncertainty` is the standard uncertainty of the measurement.
    """

    id: SnapId
    kind: SnapKind
    value: float
    measured: float
    uncertainty: float
    target: AxisName | None = None


@dataclass(frozen=True)
class SnapOutcome:
    fit: ConstrainedFit
    constraints: Constraints
    snaps: list[AppliedSnap]


def angle_to_axis_deg(direction: npt.ArrayLike, axis: npt.ArrayLike) -> float:
    """Angle between a direction and an axis line, 0 to 90 degrees (sign-free)."""
    cosine = min(abs(float(unit(direction) @ unit(axis))), 1.0)
    return float(np.degrees(np.arccos(cosine)))


def parallel_global_axis(direction: npt.ArrayLike, max_angle_deg: float = 1e-6) -> AxisName | None:
    """The global axis the direction is parallel to (either sign), if any."""
    for name, axis in GLOBAL_AXES.items():
        if angle_to_axis_deg(direction, axis) <= max_angle_deg:
            return name
    return None


def _direction_snap(direction: FloatArray, uncertainty_deg: float) -> AppliedSnap | None:
    """Parallel to the nearest global axis, else perpendicular to one, inside the window."""
    angles = {name: angle_to_axis_deg(direction, axis) for name, axis in GLOBAL_AXES.items()}
    nearest = min(angles, key=angles.__getitem__)
    parallel = snap_angle(
        angles[nearest], uncertainty_deg, floor_deg=DIRECTION_WINDOW_DEG, candidates=(0.0,)
    )
    if parallel is not None:
        return AppliedSnap(
            id="direction",
            kind="direction",
            value=0.0,
            measured=angles[nearest],
            uncertainty=uncertainty_deg,
            target=nearest,
        )
    farthest = max(angles, key=angles.__getitem__)
    square = snap_angle(
        angles[farthest], uncertainty_deg, floor_deg=DIRECTION_WINDOW_DEG, candidates=(90.0,)
    )
    if square is not None:
        return AppliedSnap(
            id="direction",
            kind="direction",
            value=90.0,
            measured=angles[farthest],
            uncertainty=uncertainty_deg,
            target=farthest,
        )
    return None


def _value(primitive: Primitive, name: SnapId) -> float | None:
    match primitive, name:
        case Plane(origin=origin, normal=normal), "offset":
            return float(np.asarray(origin) @ np.asarray(normal))
        case ((Sphere(radius=radius) | Cylinder(radius=radius)), "radius"):
            return float(radius)
        case Cone(half_angle=half_angle), "halfAngle":
            return float(np.degrees(half_angle))
        case Torus(major_radius=major), "majorRadius":
            return float(major)
        case Torus(minor_radius=minor), "minorRadius":
            return float(minor)
    return None


def _is_fixed(c: Constraints, name: SnapId) -> bool:
    match name:
        case "direction":
            return c.direction is not None or c.perpendicular_to is not None
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


def _constrain(c: Constraints, snap: AppliedSnap) -> Constraints:
    match snap.id:
        case "direction":
            assert snap.target is not None
            axis = GLOBAL_AXES[snap.target]
            if snap.value == 0.0:
                return replace(c, direction=axis, perpendicular_to=None)
            return replace(c, perpendicular_to=axis)
        case "offset":
            return replace(c, offset=snap.value)
        case "radius":
            return replace(c, radius=snap.value)
        case "halfAngle":
            return replace(c, half_angle=float(np.radians(snap.value)))
        case "majorRadius":
            return replace(c, major_radius=snap.value)
        case "minorRadius":
            return replace(c, minor_radius=snap.value)


def _value_snap(fit: ConstrainedFit, name: SnapId, units: SnapUnits) -> AppliedSnap | None:
    measured = _value(fit.primitive, name)
    if measured is None:
        return None
    if name == "offset":
        direction = direction_of(fit.primitive)
        # An offset is a design value only for planes parallel to an origin plane.
        if direction is None or parallel_global_axis(direction) is None:
            return None
    uncertainty = fit.uncertainty.get(name, 0.0)
    if name == "halfAngle":
        angle = snap_angle(measured, uncertainty, candidates=CONE_HALF_ANGLES_DEG)
        if angle is None:
            return None
        return AppliedSnap(
            id=name, kind="angle", value=angle.value, measured=measured, uncertainty=uncertainty
        )
    length = snap_length(abs(measured), uncertainty, units=units)
    if length is None or (length.value == 0.0 and name != "offset"):
        return None
    value = float(np.copysign(length.value, measured))
    return AppliedSnap(
        id=name, kind="length", value=value, measured=measured, uncertainty=uncertainty
    )


def snap_fit(
    base: ConstrainedFit,
    points: FloatArray,
    constraints: Constraints,
    rng: np.random.Generator,
    *,
    units: SnapUnits,
    rejected: frozenset[str] = frozenset(),
) -> SnapOutcome:
    """Apply the direction and value snaps that the data supports (module docstring)."""
    limit = base.rms * (1.0 + MAX_RMS_INCREASE) + 1e-12
    current, c = base, constraints
    snaps: list[AppliedSnap] = []
    for name in SNAP_ORDER:
        if name in rejected or _is_fixed(c, name):
            continue
        if name == "direction":
            direction = direction_of(current.primitive)
            if direction is None:
                continue
            candidate = _direction_snap(direction, current.uncertainty.get("direction", 0.0))
        else:
            candidate = _value_snap(current, name, units)
        if candidate is None:
            continue
        constrained = _constrain(c, candidate)
        try:
            trial = refine_constrained(current.primitive, points, constrained, rng)
        except FitError:
            continue
        if trial.rms <= limit:
            current, c = trial, constrained
            snaps.append(candidate)
    return SnapOutcome(fit=current, constraints=c, snaps=snaps)


def cluster_directions(
    directions: npt.ArrayLike,
    weights: npt.ArrayLike,
    tolerance_deg: float = DIRECTION_WINDOW_DEG,
    lock_global_axes: bool = True,
) -> tuple[FloatArray, npt.NDArray[np.int64]]:
    """Snap a set of feature directions to common design directions.

    Greedy sign-free clustering: the heaviest unassigned direction collects all
    directions within the tolerance; the cluster direction is the principal
    eigenvector of the weighted scatter. With `lock_global_axes` (after the
    alignment), clusters within the tolerance of X, Y or Z become that axis and
    are locked first. The remaining clusters, heaviest first, are made exactly
    perpendicular to every earlier cluster they are nearly perpendicular to.
    Returns the snapped direction per input (keeping each input's sign) and the
    cluster index per input.
    """
    d = unit(np.asarray(directions, dtype=np.float64).reshape(-1, 3))
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    cos_t = np.cos(np.radians(tolerance_deg))
    sin_t = np.sin(np.radians(tolerance_deg))
    cluster = np.full(len(d), -1, dtype=np.int64)
    representatives: list[FloatArray] = []
    for i in np.argsort(-w, kind="stable"):
        if cluster[i] >= 0:
            continue
        members = (cluster < 0) & (np.abs(d @ d[i]) > cos_t)
        scatter = (w[members, None] * d[members]).T @ d[members]
        representatives.append(np.linalg.eigh(scatter)[1][:, -1])
        cluster[members] = len(representatives) - 1
    locked = np.zeros(len(representatives), dtype=bool)
    if lock_global_axes:
        for index, representative in enumerate(representatives):
            for axis in GLOBAL_AXES.values():
                if abs(float(axis @ representative)) > cos_t:
                    representatives[index] = axis * np.sign(axis @ representative)
                    locked[index] = True
    cluster_weight = np.array([w[cluster == k].sum() for k in range(len(representatives))])
    settled = [representatives[k] for k in np.nonzero(locked)[0]]
    free = np.nonzero(~locked)[0]
    for k in free[np.argsort(-cluster_weight[free], kind="stable")]:
        r = representatives[k]
        for _ in range(2):  # twice, so a direction can become perpendicular to two others
            for other in settled:
                if abs(float(r @ other)) < sin_t:
                    r = unit(r - (r @ other) * other)
        representatives[k] = r
        settled.append(r)
    snapped = np.array(
        [representatives[k] * np.sign(representatives[k] @ d[i]) for i, k in enumerate(cluster)]
    ).reshape(-1, 3)
    return snapped, cluster
