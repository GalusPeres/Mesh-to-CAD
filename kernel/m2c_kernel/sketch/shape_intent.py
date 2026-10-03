"""Design values of a fitted outline shape: directions, shared centres and sizes.

A measured shape is turned into the shape a designer drew. Each design value is a
hypothesis tested on the scan: the shape is refitted with the value held fixed and
the value is kept only while the RMS stays within `KEEP_FACTOR` of the free fit
(plus a small allowance for scans whose waviness dominates the RMS). Values are
tried from the most to the least likely intent:

1. directions: axis-parallel, then multiples of 45 and 15 degrees;
2. centres: the centre of a round entity nearby (concentric with a neighbour);
3. sizes: the same size as an earlier shape, then multiples of the snap steps
   (`snapping.py`), coarsest first.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from m2c_kernel.sketch.model import FloatArray
from m2c_kernel.sketch.params import ShapeKind
from m2c_kernel.sketch.shapes import ShapeFit, fit_shape, plausible
from m2c_kernel.snapping import SnapUnits, steps_for

KEEP_FACTOR = 1.1
KEEP_ALLOWANCE = 0.25
"""The RMS may also grow by this share of the fit tolerance."""
CENTRE_REACH = 0.1
"""A neighbour's centre is tried when it lies within this share of the shape's radius
(the outer radius of a ring arm, whose own centre is poorly defined by 90 degrees of arc)."""
SIZE_REACH = 0.02
"""A design size differs from the measured one by at most this share or the tolerance.

On short arcs centre and radius are correlated: without this limit the refit would
shift the centre and accept a radius far from the measured one."""

SIZES: dict[ShapeKind, tuple[str, ...]] = {
    "circle": ("diameter",),
    "slot": ("width", "length"),
    "roundedRect": ("corner", "width", "length"),
    "ringArm": ("outer", "inner", "corner"),
}
"""Design sizes per kind, in the order they are snapped."""

DIRECTIONS: dict[ShapeKind, tuple[str, ...]] = {
    "circle": (),
    "slot": ("angle",),
    "roundedRect": ("angle",),
    "ringArm": ("start", "sweep"),
}


@dataclass(frozen=True)
class Centre:
    """The centre of a round sketch entity a new shape may share."""

    entity: str
    xy: FloatArray


@dataclass(frozen=True)
class Design:
    shape: ShapeFit
    """The shape refitted with all kept design values."""
    measured: ShapeFit
    snapped: frozenset[str] = field(default_factory=frozenset)
    """Kept design values: size names, direction names, or `centre`."""
    concentric: str | None = None
    """The entity whose centre the shape shares."""


def size_of(shape: ShapeFit, name: str) -> float:
    if name == "diameter":
        return 2.0 * shape["radius"]
    return shape[name]


def _with_size(name: str, value: float) -> dict[str, float]:
    return {"radius": value / 2.0} if name == "diameter" else {name: value}


def _direction_candidates(name: str, measured: float) -> list[float]:
    """Angles (radians) to try for a direction, most likely first."""
    period = math.pi if name == "angle" else 2.0 * math.pi
    found: list[float] = []
    for step_deg in (90.0, 45.0, 15.0):
        step = math.radians(step_deg)
        value = round(measured / step) * step
        if name == "angle":
            value = value % period
        if all(abs(value - f) > 1e-9 for f in found):
            found.append(value)
    return found


def _size_candidates(
    measured: float, preferred: Sequence[float], units: SnapUnits, tolerance: float
) -> list[float]:
    """Earlier sizes near the measurement, then multiples of the snap steps."""
    reach = max(tolerance, SIZE_REACH * measured)
    found = sorted((v for v in preferred if v > 0), key=lambda v: abs(v - measured))[:2]
    for step in steps_for(units):
        value = round(measured / step) * step
        if value > 0 and all(abs(value - f) > 1e-9 for f in found):
            found.append(value)
    return [v for v in found if abs(v - measured) <= reach]


class _Hypotheses:
    """Greedy tests of design values against the free fit's RMS."""

    def __init__(self, measured: ShapeFit, points: FloatArray, tolerance: float) -> None:
        self.points = points
        self.scale = max(tolerance / 2.0, 0.01)
        self.limit = measured.rms * KEEP_FACTOR + KEEP_ALLOWANCE * tolerance
        self.current = measured
        self.fixed: dict[str, float] = {}

    def attempt(self, values: Mapping[str, float]) -> bool:
        trial = fit_shape(
            self.current.kind,
            self.points,
            {**self.current.values, **values},
            self.scale,
            {**self.fixed, **values},
        )
        if trial.rms > self.limit or not plausible(trial, self.points):
            return False
        self.current = trial
        self.fixed.update(values)
        return True


def design(
    measured: ShapeFit,
    points: FloatArray,
    tolerance: float,
    units: SnapUnits,
    preferred: Mapping[str, Sequence[float]] | None = None,
    centres: Sequence[Centre] = (),
) -> Design:
    """The measured shape with every design value the scan supports.

    `preferred` holds sizes of earlier shapes of the same kind, by size name.
    """
    preferred = preferred or {}
    tests = _Hypotheses(measured, points, tolerance)
    snapped: set[str] = set()
    for name in DIRECTIONS[measured.kind]:
        for value in _direction_candidates(name, measured[name]):
            if tests.attempt({name: value}):
                snapped.add(name)
                break
    concentric = None
    if measured.kind in ("circle", "ringArm"):
        radius = measured["radius"] if measured.kind == "circle" else measured["outer"]
        near = sorted(
            (c for c in centres if np.linalg.norm(c.xy - measured.center) < CENTRE_REACH * radius),
            key=lambda c: float(np.linalg.norm(c.xy - measured.center)),
        )
        for centre in near:
            if tests.attempt({"cx": float(centre.xy[0]), "cy": float(centre.xy[1])}):
                snapped.add("centre")
                concentric = centre.entity
                break
    for name in SIZES[measured.kind]:
        value = size_of(tests.current, name)
        for candidate in _size_candidates(value, preferred.get(name, ()), units, tolerance):
            if tests.attempt(_with_size(name, candidate)):
                snapped.add(name)
                break
    return Design(tests.current, measured, frozenset(snapped), concentric)
