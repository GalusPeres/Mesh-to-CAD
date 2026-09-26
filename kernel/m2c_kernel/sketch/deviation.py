"""How well sketch entities match the scan section.

- Per entity (sketch panel): the section points nearest to it, their maximum and
  RMS distance and the share within the fit tolerance. The verdict follows the one
  rule of the fit tools: at least 95 % of the points within the tolerance.
- Per sketch (rebuild): the median distance from points along each fitted entity
  to the current section. The median ignores the short stretches where an entity
  was extended past the scan (corners, closed gaps) but grows with any real shift,
  such as a new alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from m2c_kernel.sketch import fit2d
from m2c_kernel.sketch.autofit import assign_points
from m2c_kernel.sketch.model import (
    Circle,
    FloatArray,
    WorkSketch,
    entity_distances,
    entity_polyline,
)
from m2c_kernel.sketch.section import Section

PASS_SHARE = 0.95
SEARCH_LIMIT = 25.0
"""Section points farther than this from an entity do not count as its match (mm)."""
DENSE_SPACING = 0.1
ENTITY_SPACING = 0.5


@dataclass(frozen=True)
class EntityFit:
    entity: str
    points: int
    max_distance: float | None
    rms: float | None
    share: float | None
    passed: bool | None
    """None for drawn entities and entities without section points."""


def entity_fits(sketch: WorkSketch, points: FloatArray, tolerance: float) -> list[EntityFit]:
    assigned = assign_points(sketch, points, max(3.0 * tolerance, 0.3))
    result = []
    for entity in sketch.entities.values():
        own = assigned.get(entity.id)
        if entity.origin != "fit" or own is None or len(own) == 0:
            result.append(EntityFit(entity.id, 0, None, None, None, None))
            continue
        distances = entity_distances(sketch, entity, own)
        share = float(np.mean(distances <= tolerance))
        result.append(
            EntityFit(
                entity.id,
                len(own),
                float(distances.max()),
                float(math.sqrt(np.mean(distances**2))),
                share,
                share >= PASS_SHARE,
            )
        )
    return result


def dense_section(section: Section) -> FloatArray:
    """Section polylines resampled finely (distances to them are distances to the curve)."""
    parts = [fit2d.resample(p, DENSE_SPACING, True) for p in section.loops if len(p) >= 3]
    parts += [fit2d.resample(p, DENSE_SPACING, False) for p in section.chains if len(p) >= 2]
    if section.support is not None:
        parts.append(section.support)
    return np.vstack(parts) if parts else np.zeros((0, 2))


def _along(sketch: WorkSketch, entity_id: str) -> FloatArray:
    """Points along an entity every ~0.5 mm."""
    polyline = entity_polyline(sketch, sketch.entities[entity_id])
    closed = isinstance(sketch.entities[entity_id], Circle)
    length = float(np.sum(np.linalg.norm(np.diff(polyline, axis=0), axis=1)))
    if length < 1e-9:
        return polyline[:1]
    spacing = min(ENTITY_SPACING, length / 4)
    return fit2d.resample(polyline[:-1] if closed else polyline, spacing, closed)


def sketch_deviation(sketch: WorkSketch, section: Section) -> float | None:
    """Largest per-entity median distance to the section; None if the section is empty."""
    dense = dense_section(section)
    if len(dense) == 0:
        return None
    tree = cKDTree(dense)
    worst = 0.0
    for entity in sketch.entities.values():
        if entity.origin != "fit":
            continue
        distances, _ = tree.query(_along(sketch, entity.id), distance_upper_bound=SEARCH_LIMIT)
        distances = np.minimum(distances, SEARCH_LIMIT)
        worst = max(worst, float(np.median(distances)))
    return worst
