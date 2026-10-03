"""Outline fits: every template is told apart from the others and measured; contours no
template explains become chains of lines and arcs."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.recognition.chain import Chain, Edge, chain_distances, chain_points
from m2c_kernel.recognition.outline import Outline, fit_outline
from m2c_kernel.sketch.fit2d import resample
from tests.synthetic.outlines import template_contour

NOISE = 0.02

SHAPES = [
    Outline("circle", (3.0, -2.0, 4.0), 0.0),
    Outline("cutCircle", (1.0, 2.0, 3.6, 0.1, 1.6), 0.0),
    Outline("cutCircle", (0.0, 0.0, 5.0, np.pi, 0.0), 0.0),
    Outline("slot", (0.0, 1.0, 0.3, 8.0, 4.8), 0.0),
    Outline("roundedRect", (-1.0, 0.0, 0.2, 12.0, 6.0, 1.5), 0.0),
    Outline("ringSegment", (0.0, 0.0, 9.0, 14.0, 0.5, 1.2, 0.0, 1.0), 0.0),
    Outline("ringSegment", (0.0, 0.0, 9.0, 14.0, np.pi / 4, np.pi / 2, 2.0, 1.0), 0.0),
]


def scanned(chain: Chain, seed: int, spacing: float = 0.1) -> np.ndarray:
    """Points along a closed chain every `spacing` mm, with Gaussian noise."""
    points = resample(chain_points(chain, step_deg=1.0), spacing, closed=True)
    return points + np.random.default_rng(seed).normal(0.0, NOISE, points.shape)


@pytest.mark.parametrize(
    "shape", SHAPES, ids=[f"{shape.kind}-{i}" for i, shape in enumerate(SHAPES)]
)
def test_each_shape_is_recognised_and_measured(shape: Outline) -> None:
    found = fit_outline(template_contour(shape, 400, NOISE, seed=4), NOISE)
    assert found.kind == shape.kind
    assert found.rms < 3 * NOISE
    expected, measured = shape.named(), found.named()
    for name in ("radius", "cut", "length", "width", "height", "inner", "outer", "gap"):
        if name in expected:
            assert measured[name] == pytest.approx(expected[name], abs=0.1), name
    assert np.hypot(*(np.subtract(found.center, shape.center))) < 0.1


def _keyhole() -> Chain:
    """A round hole of radius 5 with a 4 mm wide straight tail to x = 15: one arc and
    three lines, sharp where the tail meets the circle."""
    meet = np.sqrt(25.0 - 4.0)
    return Chain(
        (
            Edge((meet, 2.0), (meet, -2.0), (0.0, 0.0), 5.0, True),
            Edge((meet, -2.0), (15.0, -2.0)),
            Edge((15.0, -2.0), (15.0, 2.0)),
            Edge((15.0, 2.0), (meet, 2.0)),
        )
    )


def test_unexplained_contour_becomes_lines_and_arcs() -> None:
    truth = _keyhole()
    points = scanned(truth, 5)
    found = fit_outline(points, NOISE)
    assert found.kind == "profile"
    edges = found.chain.edges
    assert sorted(edge.is_arc for edge in edges) == [False, False, False, True]
    arc = next(edge for edge in edges if edge.is_arc)
    assert arc.radius == pytest.approx(5.0, abs=0.05)
    assert np.hypot(*np.subtract(arc.centre, (0.0, 0.0))) < 0.05
    # The chain follows the contour within the noise and is closed.
    assert found.rms < 2 * NOISE
    assert np.max(chain_distances(found.chain, chain_points(truth, step_deg=1.0))) < 0.1
    for edge, following in zip(edges, edges[1:] + edges[:1], strict=True):
        assert edge.end == following.start
    _, _, width, height = found.params
    assert (width, height) == pytest.approx((20.0, 10.0), abs=0.1)


def test_a_star_is_a_free_chain_within_its_tolerance() -> None:
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    star = (5 + 2 * np.cos(5 * t))[:, None] * np.column_stack([np.cos(t), np.sin(t)])
    found = fit_outline(star, NOISE)
    assert found.kind == "profile"
    assert len(found.chain.edges) >= 10
    assert np.max(chain_distances(found.chain, star)) < 0.15
