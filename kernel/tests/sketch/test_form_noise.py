"""Sections of smoothed scans of moulded parts: smooth over a millimetre, wavy along a side.

The outline of the remote control cut at mid-height: a 46 x 115 mm rectangle with
R 2.8 corners at the top, sharp corners at the bottom, its right side 0.4 degrees off
vertical, waving by 0.04 mm along the sides, with only 0.003 mm of local scatter.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from m2c_kernel.sketch.autofit import fit_section
from m2c_kernel.sketch.deviation import entity_fits
from m2c_kernel.sketch.model import Arc, Line
from m2c_kernel.sketch.noise import local_noise, section_noise
from tests.sketch.conftest import Outline, section_of

TILT = math.radians(0.4)


def _remote_outline(seed: int) -> np.ndarray:
    shape = Outline().line((0, 0), (46, 0)).line((46, 0), (46, 112.2))
    shape.arc((43.2, 112.2), 2.8, 0, 90).line((43.2, 115), (2.8, 115))
    shape.arc((2.8, 112.2), 2.8, 90, 180).line((0, 112.2), (0, 0))
    points = shape.noisy(0.003, seed)
    x, y = points[:, 0], points[:, 1]
    # The right side leans in towards the top; both sides wave along their length.
    x = x - math.tan(TILT) * y * x / 46.0 + 0.04 * np.sin(2.0 * math.pi * y / 30.0)
    return np.column_stack([x, y])


def test_a_wavy_side_raises_the_noise_above_the_local_scatter() -> None:
    section = section_of([_remote_outline(1)], stride=1)
    assert local_noise(section) < 0.01
    assert section_noise(section) > 0.02


def test_the_remote_outline_is_four_lines_and_two_arcs_within_tolerance() -> None:
    section = section_of([_remote_outline(2)], stride=1)
    outcome = fit_section(section, None, "metric", snap=False)
    entities = list(outcome.sketch.entities.values())
    assert sorted(e.kind for e in entities) == ["arc", "arc", "line", "line", "line", "line"]
    radii = [e.radius for e in entities if isinstance(e, Arc)]
    # The waviness bends the corners too.
    assert radii == pytest.approx([2.8, 2.8], abs=0.15)
    fits = entity_fits(outcome.sketch, np.vstack(section.loops), outcome.tolerance)
    assert all(fit.passed for fit in fits), fits
    # The leaning side keeps its measured direction; the upright one is vertical.
    vertical = {ref for c in outcome.constraints if c.kind == "vertical" for ref in c.refs}
    sides = [e for e in entities if isinstance(e, Line) and abs(math.sin(e.angle)) < 0.1]
    leaning = max(sides, key=lambda e: abs(e.offset))
    upright = min(sides, key=lambda e: abs(e.offset))
    assert leaning.id not in vertical and upright.id in vertical


def test_plain_scanner_noise_is_not_inflated() -> None:
    obround = Outline().line((-20, -10), (20, -10)).arc((20, 0), 10, -90, 90)
    obround.line((20, 10), (-20, 10)).arc((-20, 0), 10, 90, 270)
    section = section_of([obround.noisy(0.02, 3)])
    assert section_noise(section) == pytest.approx(local_noise(section), rel=0.25)
