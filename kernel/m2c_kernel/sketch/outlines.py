"""Closed section outlines as shapes, for the click fit and the automatic fit.

`add_shape` recognises the shape of one outline (`shapes.choose`), gives it design
values (`shape_intent.design`, with the sizes of the shapes already in the sketch
preferred, so equal buttons get equal sizes) and adds its entities. `outline_at`
finds the outline a click lies in; `entities_on` the entities already fitted to it.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from m2c_kernel.sketch.fit2d import point_in_polygon, signed_area
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    FloatArray,
    WorkSketch,
    entity_distances,
    entity_polyline,
)
from m2c_kernel.sketch.params import ShapeKind
from m2c_kernel.sketch.section import Section
from m2c_kernel.sketch.shape_entities import BuiltShape, IdTaker, build, sizes
from m2c_kernel.sketch.shape_intent import Centre, Design, design
from m2c_kernel.sketch.shapes import choose
from m2c_kernel.snapping import SnapUnits

CLICK_LENIENCY = 2.0
"""A click asks for a shape: it accepts a shape this many times looser than the auto fit."""
MIN_CENTRE_RADIUS = 1.0
"""Arcs smaller than this (corner roundings) offer no centre to share (mm)."""


@dataclass(frozen=True)
class Outline:
    raw: FloatArray
    """The section polyline as cut (closed, first point not repeated)."""
    samples: FloatArray
    """Resampled at equal spacing."""


def preferred_sizes(sketch: WorkSketch, kind: ShapeKind) -> dict[str, list[float]]:
    """Sizes of the shapes of this kind already in the sketch, by size name."""
    result: dict[str, list[float]] = {}
    for shape in sketch.shapes:
        if shape.kind != kind:
            continue
        for name, value in sizes(sketch, shape).items():
            result.setdefault(name, []).append(value)
    return result


def round_centres(sketch: WorkSketch, exclude: Collection[str] = ()) -> list[Centre]:
    return [
        Centre(e.id, e.center.copy())
        for e in sketch.entities.values()
        if isinstance(e, Arc | Circle)
        and e.origin == "fit"
        and e.radius >= MIN_CENTRE_RADIUS
        and e.id not in exclude
    ]


def add_shape(
    sketch: WorkSketch,
    outline: Outline,
    support: FloatArray,
    tolerance: float,
    units: SnapUnits,
    take: IdTaker,
    leniency: float = 1.0,
    designed: bool = True,
) -> BuiltShape | None:
    """Add the shape of one closed outline, or return None for a free profile.

    `support` are further scan points of the section (they are assigned to the new
    entities when they lie near the outline). `designed=False` keeps the measured
    values (no design values, no snaps).
    """
    centres = round_centres(sketch)
    measured = choose(outline.samples, tolerance, [c.xy for c in centres], leniency)
    if measured is None:
        return None
    result = (
        design(
            measured,
            outline.samples,
            tolerance,
            units,
            preferred_sizes(sketch, measured.kind),
            centres,
        )
        if designed
        else Design(measured, measured)
    )
    built = build(sketch, take, result)
    _assign(sketch, built.shape.entities, np.vstack([outline.samples, support]), tolerance)
    return built


def _assign(sketch: WorkSketch, ids: Sequence[str], points: FloatArray, tolerance: float) -> None:
    """Each point near the new entities becomes a sample of the nearest one."""
    entities = [sketch.entities[e] for e in ids]
    distances = np.stack([entity_distances(sketch, e, points) for e in entities])
    nearest = np.argmin(distances, axis=0)
    near = distances[nearest, np.arange(len(points))] <= max(3.0 * tolerance, 0.3)
    for k, entity in enumerate(entities):
        sketch.samples[entity.id] = points[(nearest == k) & near]


def outline_at(section: Section, point: FloatArray) -> FloatArray | None:
    """The smallest closed section outline around a point, or None."""
    around = [loop for loop in section.loops if len(loop) >= 3 and point_in_polygon(point, loop)]
    if not around:
        return None
    return min(around, key=lambda loop: abs(signed_area(loop)))


def entities_on(sketch: WorkSketch, samples: FloatArray, band: float) -> list[str]:
    """Fitted entities that run along an outline (median distance within `band`)."""
    tree = cKDTree(samples)
    result = []
    for entity in sketch.entities.values():
        if entity.origin != "fit":
            continue
        distances, _ = tree.query(entity_polyline(sketch, entity))
        if float(np.median(distances)) <= band:
            result.append(entity.id)
    return result


def support_near(section: Section, samples: FloatArray, band: float) -> FloatArray:
    """The section's support points within `band` of an outline."""
    if section.support is None or len(section.support) == 0:
        return np.zeros((0, 2))
    distances, _ = cKDTree(samples).query(section.support, distance_upper_bound=band)
    result: FloatArray = section.support[np.isfinite(distances)]
    return result
