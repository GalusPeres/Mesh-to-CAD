"""Region labels (one uint16 per face, 0 = unassigned) and their colouring.

Labels stay disjoint by construction: every operation writes one array. Colours
are palette indices chosen greedily so that adjacent regions differ; regions
that already have a colour keep it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import numpy.typing as npt

from m2c_kernel.segmentation.analysis import IntArray

PALETTE_SIZE = 10
"""Number of region colours in the renderer palette (`viewport/palette.ts`)."""

type LabelArray = npt.NDArray[np.uint16]


def adjacency(labels: LabelArray, pairs: IntArray) -> set[tuple[int, int]]:
    """Pairs (a, b), a < b, of labels that share at least one mesh edge (0 excluded)."""
    la = labels[pairs[:, 0]].astype(np.int64)
    lb = labels[pairs[:, 1]].astype(np.int64)
    mask = (la != lb) & (la > 0) & (lb > 0)
    low, high = np.minimum(la[mask], lb[mask]), np.maximum(la[mask], lb[mask])
    keys = np.unique(low * 65_536 + high)
    return {(int(key // 65_536), int(key % 65_536)) for key in keys}


def assign_colors(
    labels: Iterable[int],
    neighbours: set[tuple[int, int]],
    existing: Mapping[int, int],
    sizes: Mapping[int, int] | None = None,
) -> dict[int, int]:
    """Palette index per label: existing ones are kept, new ones avoid their neighbours.

    New labels are coloured largest first; when all colours are taken by
    neighbours, the least used one among them is chosen.
    """
    graph: dict[int, set[int]] = {}
    for a, b in neighbours:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    colors = {label: color for label, color in existing.items()}
    pending = [label for label in labels if label not in colors]
    if sizes is not None:
        pending.sort(key=lambda label: -sizes.get(label, 0))
    for label in pending:
        used = [colors[other] for other in graph.get(label, ()) if other in colors]
        free = [color for color in range(PALETTE_SIZE) if color not in used]
        if free:
            # rotate the start so that unrelated regions do not all get colour 0
            colors[label] = free[label % len(free)] if len(free) > 1 else free[0]
        else:
            counts = np.bincount(used, minlength=PALETTE_SIZE)
            colors[label] = int(np.argmin(counts))
    return colors


def face_stats(labels: LabelArray, areas: npt.NDArray[np.float64]) -> tuple[IntArray, IntArray]:
    """Face count and area (as float) per label value."""
    counts = np.bincount(labels, minlength=1).astype(np.int64)
    area = np.bincount(labels, weights=areas, minlength=1)
    return counts, area


def next_free_label(used: Iterable[int], limit: int) -> int | None:
    taken = set(used)
    return next((label for label in range(1, limit + 1) if label not in taken), None)
