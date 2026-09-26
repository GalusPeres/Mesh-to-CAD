"""Region labels (one uint16 per face, 0 = unassigned) and their colouring.

Labels stay disjoint by construction: every operation writes one array. Colours
are palette indices chosen so that adjacent regions differ; regions that already
have a colour keep it unless a larger neighbour holds the same one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import numpy.typing as npt

from m2c_kernel.segmentation.analysis import IntArray

PALETTE_SIZE = 10
"""Number of region colours in the renderer palette (`viewport/palette.ts`).

The palette is ordered by hue, so palette indices that are far apart on the
cycle are also far apart in colour."""
MATCH_IOU = 0.5
"""A new region inherits id, name and colour of an old one it overlaps more than this (IoU)."""

type LabelArray = npt.NDArray[np.uint16]


def adjacency(labels: LabelArray, pairs: IntArray) -> set[tuple[int, int]]:
    """Pairs (a, b), a < b, of labels that share at least one mesh edge (0 excluded)."""
    la = labels[pairs[:, 0]].astype(np.int64)
    lb = labels[pairs[:, 1]].astype(np.int64)
    mask = (la != lb) & (la > 0) & (lb > 0)
    low, high = np.minimum(la[mask], lb[mask]), np.maximum(la[mask], lb[mask])
    keys = np.unique(low * 65_536 + high)
    return {(int(key // 65_536), int(key % 65_536)) for key in keys}


def _cyclic_distance(a: int, b: int) -> int:
    step = abs(a - b) % PALETTE_SIZE
    return min(step, PALETTE_SIZE - step)


def assign_colors(
    labels: Iterable[int],
    neighbours: set[tuple[int, int]],
    existing: Mapping[int, int],
    sizes: Mapping[int, float],
) -> dict[int, int]:
    """Palette index per label so that adjacent labels differ.

    Labels in `existing` keep their colour unless a larger neighbour keeps the
    same one. The others are coloured most-constrained first (DSatur), each with
    the colour farthest on the hue cycle from its coloured neighbours; ties go to
    the least used colour. Only a label with ten or more differently coloured
    neighbours can end up sharing a colour with one of them.
    """
    wanted = sorted(set(labels))
    graph: dict[int, set[int]] = {label: set() for label in wanted}
    for a, b in neighbours:
        if a in graph and b in graph:
            graph[a].add(b)
            graph[b].add(a)

    colors: dict[int, int] = {}
    for label in sorted(
        (label for label in wanted if label in existing), key=lambda item: -sizes.get(item, 0.0)
    ):
        color = existing[label] % PALETTE_SIZE
        if all(colors.get(other) != color for other in graph[label]):
            colors[label] = color

    usage = np.bincount(list(colors.values()), minlength=PALETTE_SIZE).tolist()
    neighbour_colors: dict[int, set[int]] = {
        label: {colors[other] for other in graph[label] if other in colors} for label in wanted
    }
    pending = {label for label in wanted if label not in colors}
    while pending:
        label = max(
            pending,
            key=lambda item: (len(neighbour_colors[item]), sizes.get(item, 0.0), -item),
        )
        pending.remove(label)
        taken = neighbour_colors[label]
        candidates = [color for color in range(PALETTE_SIZE) if color not in taken]
        if not candidates:
            candidates = list(range(PALETTE_SIZE))

        def preference(color: int, taken: set[int] = taken) -> tuple[int, int, int]:
            spread = min((_cyclic_distance(color, other) for other in taken), default=0)
            return (spread, -usage[color], -color)

        color = max(candidates, key=preference)
        colors[label] = color
        usage[color] += 1
        for other in graph[label]:
            neighbour_colors[other].add(color)
    return colors


def label_sizes(
    labels: LabelArray, areas: npt.NDArray[np.float64], count: int
) -> tuple[IntArray, npt.NDArray[np.float64]]:
    """Face count and area per label value 0 .. count (index = label)."""
    counts = np.bincount(labels, minlength=count + 1).astype(np.int64)
    area = np.bincount(labels, weights=areas, minlength=count + 1)
    return counts, area


def free_labels(used: Iterable[int], count: int, limit: int) -> list[int] | None:
    """The `count` smallest label values above 0 not in `used`, or None beyond `limit`."""
    taken = set(used)
    result: list[int] = []
    label = 1
    while len(result) < count:
        if label > limit:
            return None
        if label not in taken:
            result.append(label)
        label += 1
    return result


def match_regions(old: LabelArray, new: LabelArray) -> dict[int, int]:
    """New label -> old label for pairs whose faces overlap with IoU above one half.

    With IoU above one half each label can match at most one label of the other
    array, so the result is a one-to-one map.
    """
    both = (old > 0) & (new > 0)
    if not both.any():
        return {}
    old_counts = np.bincount(old)
    new_counts = np.bincount(new)
    keys = old[both].astype(np.int64) * 65_536 + new[both].astype(np.int64)
    pair_keys, shared = np.unique(keys, return_counts=True)
    result: dict[int, int] = {}
    for key, overlap in zip(pair_keys, shared, strict=True):
        old_label, new_label = int(key // 65_536), int(key % 65_536)
        union = old_counts[old_label] + new_counts[new_label] - overlap
        if overlap > MATCH_IOU * union:
            result[new_label] = old_label
    return result
