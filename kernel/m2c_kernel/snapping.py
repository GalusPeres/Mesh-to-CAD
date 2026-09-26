"""Design-intent value snapping shared by fits and sketches.

A measured value snaps to a "design" value only if that value lies inside the
snap window: three times the measurement's standard uncertainty, but at least a
small floor. Candidates are tried from the most to the least likely intent:
preferred values first (for example the radius of a neighbouring feature), then
multiples of the coarsest step. Metric parts snap to 5 / 1 / 0.5 / 0.25 / 0.1 /
0.05 mm; inch parts to 1/4 ... 1/64 in. Angles snap to common angles only.

Callers decide whether a snap is kept (for fits: the constrained refit may raise
the RMS by at most 5 %) and report every applied snap with the measured value, so
the user can judge it (docs/DESIGN.md 5.2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

type SnapUnits = Literal["metric", "inch"]

INCH_MM = 25.4

METRIC_STEPS_MM: tuple[float, ...] = (5.0, 1.0, 0.5, 0.25, 0.1, 0.05)
INCH_STEPS_MM: tuple[float, ...] = tuple(INCH_MM / d for d in (4, 8, 16, 32, 64))
COMMON_ANGLES_DEG: tuple[float, ...] = (
    0.0,
    15.0,
    30.0,
    45.0,
    60.0,
    90.0,
    120.0,
    135.0,
    150.0,
    180.0,
)

UNCERTAINTY_FACTOR = 3.0
"""The snap window is this many standard uncertainties wide on each side."""


@dataclass(frozen=True)
class Snap:
    """A snapped value together with the measurement it replaces."""

    value: float
    measured: float
    uncertainty: float
    step: float | None
    """The step the value is a multiple of, or None for a preferred value."""


def steps_for(units: SnapUnits) -> tuple[float, ...]:
    """Step sizes in millimetres, coarsest first."""
    return INCH_STEPS_MM if units == "inch" else METRIC_STEPS_MM


def snap_window(uncertainty: float, floor: float) -> float:
    """Half width of the interval in which a design value is accepted."""
    return max(UNCERTAINTY_FACTOR * max(uncertainty, 0.0), floor)


def snap_length(
    measured: float,
    uncertainty: float,
    *,
    units: SnapUnits = "metric",
    floor: float = 0.005,
    preferred: Sequence[float] = (),
) -> Snap | None:
    """Snap a length, radius or position in millimetres; None if no candidate fits."""
    if not math.isfinite(measured):
        return None
    window = snap_window(uncertainty, floor)
    for value in preferred:
        if abs(measured - value) <= window:
            return Snap(float(value), measured, uncertainty, None)
    for step in steps_for(units):
        value = round(measured / step) * step
        if abs(measured - value) <= window:
            return Snap(float(value), measured, uncertainty, step)
    return None


def snap_angle(
    measured_deg: float,
    uncertainty_deg: float,
    *,
    floor_deg: float = 0.05,
    candidates: Sequence[float] = COMMON_ANGLES_DEG,
) -> Snap | None:
    """Snap an angle in degrees to the nearest common angle inside the window."""
    if not math.isfinite(measured_deg):
        return None
    window = snap_window(uncertainty_deg, floor_deg)
    best = min(candidates, key=lambda value: abs(measured_deg - value), default=None)
    if best is None or abs(measured_deg - best) > window:
        return None
    return Snap(float(best), measured_deg, uncertainty_deg, None)
