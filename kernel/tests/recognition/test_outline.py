"""Outline fits: every simple shape is told apart from the others and measured."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.recognition.outline import Outline, fit_outline, outline_points

NOISE = 0.02

SHAPES = [
    Outline("circle", (3.0, -2.0, 4.0), 0.0),
    Outline("slot", (0.0, 1.0, 0.3, 8.0, 4.8), 0.0),
    Outline("roundedRect", (-1.0, 0.0, 0.2, 12.0, 6.0, 1.5), 0.0),
    Outline("ringSegment", (0.0, 0.0, 9.0, 14.0, 0.5, 1.2, 0.0, 1.0), 0.0),
    Outline("ringSegment", (0.0, 0.0, 9.0, 14.0, np.pi / 4, np.pi / 2, 2.0, 1.0), 0.0),
]


@pytest.mark.parametrize(
    "shape", SHAPES, ids=[f"{shape.kind}-{i}" for i, shape in enumerate(SHAPES)]
)
def test_each_shape_is_recognised_and_measured(shape: Outline) -> None:
    rng = np.random.default_rng(4)
    points = outline_points(shape, 400)
    points = points + rng.normal(0.0, NOISE, points.shape)
    found = fit_outline(points, NOISE)
    assert found.kind == shape.kind
    assert found.rms < 3 * NOISE
    expected, measured = shape.named(), found.named()
    for name in ("radius", "length", "width", "height", "inner", "outer", "gap"):
        if name in expected:
            assert measured[name] == pytest.approx(expected[name], abs=0.1), name
    assert np.hypot(*(np.subtract(found.center, shape.center))) < 0.1


def test_unexplained_contour_becomes_a_free_profile() -> None:
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    star = (5 + 2 * np.cos(5 * t))[:, None] * np.column_stack([np.cos(t), np.sin(t)])
    assert fit_outline(star, NOISE).kind == "profile"
