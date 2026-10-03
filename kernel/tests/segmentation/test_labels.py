"""Region labels: adjacency, colouring, free label values and region matching."""

from __future__ import annotations

import numpy as np

from m2c_kernel.segmentation.labels import (
    PALETTE_SIZE,
    adjacency,
    assign_colors,
    free_labels,
    match_regions,
)


def _grid_pairs(width: int, height: int) -> np.ndarray:
    """Face pairs of a width x height grid of cells (4-neighbourhood)."""
    index = np.arange(width * height).reshape(height, width)
    horizontal = np.stack([index[:, :-1].ravel(), index[:, 1:].ravel()], axis=1)
    vertical = np.stack([index[:-1, :].ravel(), index[1:, :].ravel()], axis=1)
    return np.concatenate([horizontal, vertical]).astype(np.int64)


def test_adjacency_lists_each_touching_pair_once_and_ignores_unassigned() -> None:
    labels = np.array([1, 1, 2, 0, 3, 3], dtype=np.uint16)
    pairs = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [2, 1]])
    assert adjacency(labels, pairs) == {(1, 2)}


def test_neighbours_never_share_a_colour_on_a_dense_map() -> None:
    rng = np.random.default_rng(3)
    width, height = 40, 40
    # random blobs: each cell takes the label of the nearest of 60 random centres
    centres = rng.uniform(0, 40, (60, 2))
    y, x = np.mgrid[0:height, 0:width]
    cells = np.stack([x.ravel(), y.ravel()], axis=1)
    nearest = np.argmin(((cells[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
    labels = (nearest + 1).astype(np.uint16)
    neighbours = adjacency(labels, _grid_pairs(width, height))
    sizes = {int(label): float(count) for label, count in enumerate(np.bincount(labels)) if count}
    colors = assign_colors(sizes.keys(), neighbours, {}, sizes)
    assert set(colors) == set(sizes)
    assert all(0 <= color < PALETTE_SIZE for color in colors.values())
    assert all(colors[a] != colors[b] for a, b in neighbours)
    # the palette is used broadly, not just two or three colours
    assert len(set(colors.values())) >= 6


def test_existing_colours_are_kept_unless_a_larger_neighbour_holds_them() -> None:
    neighbours = {(1, 2), (2, 3)}
    sizes = {1: 100.0, 2: 10.0, 3: 50.0}
    colors = assign_colors([1, 2, 3], neighbours, {1: 4, 2: 4, 3: 7}, sizes)
    assert colors[1] == 4
    assert colors[3] == 7
    assert colors[2] not in (4, 7)


def test_a_new_region_takes_a_colour_far_from_its_neighbours() -> None:
    colors = assign_colors([1, 2], {(1, 2)}, {1: 0}, {1: 5.0, 2: 1.0})
    # index distance on the hue cycle of ten colours: 5 is the farthest from 0
    assert colors[2] == 5


def test_free_labels_fill_gaps_first_and_respect_the_limit() -> None:
    assert free_labels({1, 2, 4}, 3, 100) == [3, 5, 6]
    assert free_labels({1, 2}, 2, 3) is None


def test_regions_match_when_they_overlap_by_more_than_half() -> None:
    old = np.array([1, 1, 1, 1, 2, 2, 0, 0], dtype=np.uint16)
    new = np.array([5, 5, 5, 6, 6, 6, 6, 0], dtype=np.uint16)
    # 5 and old 1 share 3 of 4 faces (IoU 0.75); 6 and old 2 share 2 of 4 (IoU 0.5, no match)
    assert match_regions(old, new) == {5: 1}
    assert match_regions(old, np.zeros_like(old)) == {}
