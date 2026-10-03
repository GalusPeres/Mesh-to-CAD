"""Template chains: closed chains of lines and arcs that lie on their shape's boundary."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.recognition.chain import chain_points
from m2c_kernel.recognition.shapes import DISTANCES, PARAMETERS, Template
from m2c_kernel.recognition.templates import template_chain

SHAPES: list[tuple[Template, tuple[float, ...]]] = [
    ("circle", (3.0, -2.0, 4.0)),
    ("cutCircle", (1.0, 2.0, 3.6, 0.1, 1.6)),
    ("cutCircle", (0.0, 0.0, 5.0, np.pi, -1.0)),
    ("slot", (0.0, 1.0, 0.3, 8.0, 4.8)),
    ("roundedRect", (-1.0, 0.0, 0.2, 12.0, 6.0, 1.5)),
    ("roundedRect", (2.0, 1.0, 0.0, 10.0, 4.0, 0.0)),
    ("ringSegment", (0.0, 0.0, 9.0, 14.0, 0.5, 1.2, 0.0, 0.0)),
    ("ringSegment", (0.0, 0.0, 8.65, 13.35, np.pi / 4, np.pi / 2, 5.9, 0.8)),
]


def _named(kind: Template, values: tuple[float, ...]) -> dict[str, float]:
    return dict(zip(PARAMETERS[kind], values, strict=True))


@pytest.mark.parametrize("shape", SHAPES, ids=[f"{kind}-{i}" for i, (kind, _) in enumerate(SHAPES)])
def test_chain_lies_on_the_template_boundary(shape: tuple[Template, tuple[float, ...]]) -> None:
    kind, values = shape
    chain = template_chain(kind, _named(kind, values))
    points = chain_points(chain, step_deg=1.0)
    # The ring segment's distance is approximate at rounded corners (#15); its chain is
    # checked by the area of its sketch in test_build.py.
    if not (kind == "ringSegment" and values[7] > 0.0):
        assert np.abs(DISTANCES[kind](values, points)).max() < 1e-6
    edges = chain.edges
    for edge, following in zip(edges, edges[1:] + edges[:1], strict=True):
        assert edge.end == following.start
    x, y = points[:, 0], points[:, 1]
    assert 0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1)) > 0.0, "counter-clockwise"


def test_a_cut_circle_keeps_sharp_corners_on_its_cut() -> None:
    chain = template_chain("cutCircle", _named("cutCircle", (0.0, 0.0, 4.0, 0.0, 2.0)))
    arc, line = chain.edges
    assert arc.is_arc and not line.is_arc
    assert arc.radius == 4.0
    assert line.start[0] == pytest.approx(2.0) and line.end[0] == pytest.approx(2.0)
    assert abs(line.start[1] - line.end[1]) == pytest.approx(2.0 * np.sqrt(12.0))
    assert not any(kind == "tangent" for kind, _ in chain.relations)
