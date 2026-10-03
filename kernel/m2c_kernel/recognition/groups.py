"""Groups of equal features, and the one top-edge rounding each group shares.

Features of the same shape, size, height and top on the same plane are made alike: the
panel lists them as one row, and their top edges share one radius (design intent): the
median of the members' measured radii, snapped to a design value.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.fitting.corner import EdgeRadius
from m2c_kernel.snapping import SnapUnits, snap_length

if TYPE_CHECKING:
    from m2c_kernel.recognition.api import Feature

SIZE_DECIMALS = 3


def feature_groups(features: Sequence[Feature]) -> tuple[int, ...]:
    """Per feature its group number (0, 1, ... in order of first appearance)."""
    groups: dict[tuple[object, ...], int] = {}
    result = []
    for index, feature in enumerate(features):
        relief, outline = feature.relief, feature.outline
        size = tuple(
            round(value, SIZE_DECIMALS)
            for name, value in outline.named().items()
            if name not in ("cx", "cy", "angle", "start")
        )
        # Free profiles differ from each other: each is its own group.
        shape = (outline.kind, size) if outline.kind != "profile" else ("profile", index)
        key = (feature.plane, relief.kind, relief.top, shape, round(relief.height, SIZE_DECIMALS))
        result.append(groups.setdefault(key, len(groups)))
    return tuple(result)


def group_radii(
    groups: Sequence[int], roundings: Sequence[EdgeRadius | None], units: SnapUnits = "metric"
) -> tuple[float | None, ...]:
    """Per group the radius its members' top edges share; 0 sharp, None not measured."""
    count = max(groups, default=-1) + 1
    members: list[list[EdgeRadius]] = [[] for _ in range(count)]
    for group, rounding in zip(groups, roundings, strict=True):
        if rounding is not None:
            members[group].append(rounding)
    return tuple(shared_radius(measured, units) for measured in members)


def shared_radius(measured: Sequence[EdgeRadius], units: SnapUnits = "metric") -> float | None:
    """One radius for equal edges: the median of the measured ones, snapped."""
    if not measured:
        return None
    radii = np.array([rounding.radius for rounding in measured])
    median = float(np.median(radii))
    if median <= 0.0:
        return 0.0
    spread = 1.4826 * float(np.median(np.abs(radii - median)))
    within = float(np.median([rounding.uncertainty for rounding in measured]))
    uncertainty = max(spread / np.sqrt(len(radii)), within)
    snap = snap_length(median, uncertainty, units=units)
    return snap.value if snap is not None and snap.value > 0.0 else median
