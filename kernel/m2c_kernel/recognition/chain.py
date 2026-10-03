"""Outlines as closed chains of lines and arcs: the geometry a sketch is built from.

Every recognised outline is a chain. A template's chain follows from its parameters
(`templates.py`); a free contour is split into lines and arcs by the section
sketch's fitter (`sketch/autofit.py`): a globally optimal split into lines and arcs,
tangency, parallels and equal radii where the scan shows them, a joint refit, round
values and exact junctions, so corners lie where neighbouring entities meet (a
button cut by the part's outline keeps its sharp corners on the cut).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.sketch.autofit import fit_section
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    WorkSketch,
    arc_distances,
    arc_points,
    segment_distances,
)
from m2c_kernel.sketch.section import Section

type Relation = tuple[str, tuple[int, ...]]

MIN_EDGE_MM = 1e-3
"""Shorter edges are dropped: the solver may shrink a line between two tangent arcs."""


@dataclass(frozen=True)
class Edge:
    """A line (no centre) or an arc from `start` to `end`.

    A lone arc that ends where it starts is a full circle.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    centre: tuple[float, float] | None = None
    radius: float = 0.0
    ccw: bool = True

    @property
    def is_arc(self) -> bool:
        return self.centre is not None


@dataclass(frozen=True)
class Chain:
    """A closed chain: edge i ends where edge i + 1 starts (the last one at the first).

    `relations` are sketch constraints between edges (kind, edge indices): tangency,
    parallels, equal radii and the like.
    """

    edges: tuple[Edge, ...]
    relations: tuple[Relation, ...] = ()

    @property
    def is_circle(self) -> bool:
        return len(self.edges) == 1 and self.edges[0].is_arc


def point(xy: FloatArray) -> tuple[float, float]:
    return float(xy[0]), float(xy[1])


def edge_points(edge: Edge, step_deg: float = 3.0) -> FloatArray:
    """Points along an edge, both ends included."""
    start, end = np.array(edge.start), np.array(edge.end)
    if edge.centre is None:
        return np.vstack([start, end])
    return arc_points(np.array(edge.centre), edge.radius, start, end, edge.ccw, step_deg)


def chain_points(chain: Chain, step_deg: float = 3.0) -> FloatArray:
    """Points along the closed chain, each junction once, the start not repeated."""
    parts = [edge_points(edge, step_deg)[:-1] for edge in chain.edges]
    return np.vstack(parts) if parts else np.zeros((0, 2))


def chain_distances(chain: Chain, points: FloatArray) -> FloatArray:
    """Distance of every point to the nearest edge of the chain."""
    distances = []
    for edge in chain.edges:
        start, end = np.array(edge.start), np.array(edge.end)
        if edge.centre is None:
            distances.append(segment_distances(points, start, end))
        else:
            centre = np.array(edge.centre)
            distances.append(arc_distances(points, centre, edge.radius, start, end, edge.ccw))
    result: FloatArray = np.min(np.stack(distances), axis=0)
    return result


def chain_size(chain: Chain) -> tuple[float, float, float, float]:
    """Centre and extent (width, height) of the chain's bounding box in the plane frame."""
    points = chain_points(chain)
    low, high = points.min(axis=0), points.max(axis=0)
    centre, extent = (low + high) / 2.0, high - low
    return float(centre[0]), float(centre[1]), float(extent[0]), float(extent[1])


def free_chain(contour: FloatArray, tolerance: float) -> Chain:
    """Lines and arcs through a closed contour, every point within `tolerance` of them."""
    outcome = fit_section(Section(loops=[contour], chains=[]), tolerance, "metric")
    return _as_chain(outcome.sketch, outcome.constraints)


def _as_chain(sketch: WorkSketch, constraints: list[Constraint]) -> Chain:
    """The single closed loop of a fitted sketch, in order, without degenerate edges."""
    entities = list(sketch.entities.values())
    circle = next((e for e in entities if isinstance(e, Circle)), None)
    if circle is not None:
        on = point(circle.center + np.array([circle.radius, 0.0]))
        return Chain((Edge(on, on, point(circle.center), circle.radius),))
    by_start = {entity.start: entity for entity in entities if not isinstance(entity, Circle)}
    first = next(e for e in entities if not isinstance(e, Circle))
    ordered = [first]
    while len(ordered) < len(by_start):
        following = by_start.get(ordered[-1].end)
        if following is None or following is first:
            break
        ordered.append(following)
    edges: list[Edge] = []
    index: dict[str, int] = {}
    for entity in ordered:
        start, end = point(sketch.xy(entity.start)), point(sketch.xy(entity.end))
        if math.dist(start, end) < MIN_EDGE_MM:
            continue  # the neighbours meet at this point already
        index[entity.id] = len(edges)
        if isinstance(entity, Arc):
            edges.append(Edge(start, end, point(entity.center), float(entity.radius), entity.ccw))
        else:
            edges.append(Edge(start, end))
    # Dropped edges leave their neighbours a hair apart: close the chain exactly.
    closed = [
        Edge(edges[i - 1].end, edge.end, edge.centre, edge.radius, edge.ccw)
        for i, edge in enumerate(edges)
    ]
    relations = tuple(
        (c.kind, tuple(index[ref] for ref in c.refs))
        for c in constraints
        if all(ref in index for ref in c.refs)
    )
    return Chain(tuple(closed), relations)
