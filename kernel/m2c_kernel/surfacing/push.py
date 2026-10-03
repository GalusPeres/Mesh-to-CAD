"""Push a net's open border past reference faces (QuickSurface: Offset by reference surfaces).

Trimming against the faces then cuts cleanly instead of grazing along them.

A border point of the net whose limit point lies within `reach` of a plane or of a
face of a body and not yet `tolerance` past it moves along that face's outward normal
until it is. For a plane, outward is the side away from the bulk of the net; for a
face of a body, outside the body (`cad/distance.py`). Every face counts on its own, so
a border near a corner passes both faces there. A face counts for a border point when
the point lies on it (within `tolerance`) or when the net runs towards it there: the
end of a rounding net runs into the block's end face and along its top and back, so it
passes the end face and stays on the rounding. The border control points are solved
so that their limit points land exactly there (the border is a cubic B-spline of the
border control points alone); the rest of the net stays, so its fit to the scan is
kept, and pinned points hold.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from m2c_kernel.surfacing.subdivision import EdgeTopology, edge_topology, limit_matrix

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

PASSES = 3
"""A point near two faces (a corner) is pushed past one per pass."""
HEADING = 0.5
"""cos 60 degrees: a net heading at least this much towards a face runs into it."""

type Measure = Callable[[FloatArray], tuple[float, FloatArray]]
"""Signed distance of a point (positive on the outward side) and the outward normal."""


@dataclass(frozen=True)
class Reference:
    name: str
    measure: Measure


@dataclass(frozen=True)
class PushResult:
    vertices: FloatArray
    moved: int
    """Border points that were pushed."""
    references: tuple[str, ...]
    """References that pushed at least one point."""


def plane_reference(
    name: str, origin: FloatArray, normal: FloatArray, limits: FloatArray
) -> Reference:
    """A plane whose outward side is away from most of the net's limit points."""
    origin = np.asarray(origin, dtype=np.float64)
    unit_normal = np.asarray(normal, dtype=np.float64) / np.linalg.norm(normal)
    side = float(np.mean((limits - origin) @ unit_normal))
    outward = -unit_normal if side > 0 else unit_normal

    def measure(point: FloatArray) -> tuple[float, FloatArray]:
        return float((point - origin) @ outward), outward

    return Reference(name, measure)


def push_past(
    cage: FloatArray,
    quads: IntArray,
    references: Sequence[Reference],
    *,
    tolerance: float,
    reach: float,
    fixed: npt.NDArray[np.bool_] | None = None,
) -> PushResult:
    """The net with its border pushed `tolerance` past the references within `reach`.

    `fixed` (per control point) marks pinned points: their limit points stay.
    """
    count = len(cage)
    topology = edge_topology(quads, count)
    border = np.unique(topology.edges[topology.boundary].ravel())
    if len(border) == 0 or not references:
        return PushResult(cage.copy(), 0, ())
    limits = limit_matrix(quads, count).tocsr()
    system = limits[border][:, border].tocsc()
    vertices = cage.copy()
    pushed: set[int] = set()
    used: set[str] = set()
    for _ in range(PASSES):
        positions = limits @ vertices
        current = positions[border]
        headings = _headings(positions, quads, topology)[border]
        moves = np.zeros_like(current)
        for slot, point in enumerate(current):
            if fixed is not None and fixed[border[slot]]:
                continue
            move = _move(point, headings[slot], references, tolerance, reach)
            if move is not None:
                moves[slot] = move[0]
                pushed.add(int(border[slot]))
                used.add(move[1])
        if not np.any(moves):
            break
        offsets = np.column_stack([spla.spsolve(system, moves[:, axis]) for axis in range(3)])
        vertices[border] += offsets
    return PushResult(vertices, len(pushed), tuple(sorted(used)))


def _headings(positions: FloatArray, quads: IntArray, topology: EdgeTopology) -> FloatArray:
    """Per point, the unit direction in which the net runs out at it (for border points).

    From the mean of the neighbours across inner edges to the point; a corner of the
    net has none and looks from the opposite corner of its quad.
    """
    inner = topology.edges[~topology.boundary]
    count = len(positions)
    adjacency = sp.coo_matrix(
        (np.ones(2 * len(inner)), (inner.ravel(), inner[:, ::-1].ravel())), shape=(count, count)
    ).tocsr()
    neighbours = np.asarray(adjacency.sum(axis=1)).ravel()
    origin = (adjacency @ positions) / np.maximum(neighbours, 1)[:, None]
    opposite = np.empty(count, dtype=np.int64)
    opposite[quads.ravel()] = np.roll(quads, -2, axis=1).ravel()
    lonely = neighbours == 0
    origin[lonely] = positions[opposite[lonely]]
    direction = positions - origin
    lengths = np.maximum(np.linalg.norm(direction, axis=1), 1e-12)[:, None]
    headings: FloatArray = direction / lengths
    return headings


def _move(
    point: FloatArray,
    heading: FloatArray,
    references: Sequence[Reference],
    tolerance: float,
    reach: float,
) -> tuple[FloatArray, str] | None:
    """How far a border point must move past its nearest reference, or None.

    A reference counts when the point lies on it or the net runs into it (`heading`).
    """
    best: tuple[float, float, FloatArray, str] | None = None
    for reference in references:
        distance, outward = reference.measure(point)
        if abs(distance) > reach or distance >= tolerance - 1e-9 or not np.any(outward):
            continue
        if distance < -tolerance and float(heading @ outward) < HEADING:
            continue
        if best is None or abs(distance) < best[0]:
            best = (abs(distance), distance, outward, reference.name)
    if best is None:
        return None
    _, distance, outward, name = best
    return (tolerance - distance) * outward, name
