"""Sections of the scan and lofts through them, against a tube of known volume."""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest

from m2c_kernel.cad.check import check_solid
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.loft import LoftAxis, loft_scan, scan_extent
from m2c_kernel.freeform.sections import (
    loop_area,
    normalise_section,
    section_loops,
)
from m2c_kernel.protocol.errors import KernelError
from tests.freeform.shapes import FloatArray, IntArray, tube_radii, tube_scan, tube_volume
from tests.synthetic import random_rotation

pytestmark = pytest.mark.occt

Z = np.array([0.0, 0.0, 1.0])


@cache
def tube() -> tuple[FloatArray, IntArray]:
    return tube_scan(sigma=0.02)


def test_section_of_the_tube_is_one_closed_ellipse() -> None:
    vertices, faces = tube()
    loops = section_loops(vertices, faces, np.zeros(3), Z, 30.0)
    assert len(loops) == 1
    a, b = tube_radii(np.asarray(30.0))
    assert abs(loop_area(loops[0], Z)) == pytest.approx(np.pi * a * b, rel=2e-3)
    np.testing.assert_allclose(loops[0][:, 2], 30.0, atol=1e-9)


def test_normalised_sections_are_compatible() -> None:
    vertices, faces = tube()
    reference = np.array([1.0, 0.0, 0.0])
    sections = []
    for height in (10.0, 40.0):
        loop = section_loops(vertices, faces, np.zeros(3), Z, height)[0]
        sections.append(normalise_section(loop[::-1], Z, reference, count=64))
    for points in sections:
        assert len(points) == 64
        assert loop_area(points, Z) > 0
        centre = points.mean(axis=0)
        start = points[0] - centre
        assert abs(np.degrees(np.arctan2(start[1], start[0]))) < 6.0


@pytest.mark.parametrize("count", [9, 12, 16])
def test_loft_of_the_tube_matches_the_true_volume(count: int) -> None:
    vertices, faces = tube()
    loft = loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 2.0, 58.0, count)
    check = check_solid(loft.solid.shape)
    assert check.valid and check.solids == 1
    exact = tube_volume(2.0, 58.0)
    assert abs(check.volume - exact) / exact < 2e-3
    assert loft.section_rms < 0.03
    assert len(loft.sections) == count


def test_loft_along_a_tilted_axis() -> None:
    vertices, faces = tube()
    rotation = random_rotation(np.random.default_rng(12))
    offset = np.array([30.0, -12.0, 7.0])
    posed = vertices @ rotation.T + offset
    axis = LoftAxis(offset, rotation @ Z)
    low, high = scan_extent(posed, axis)
    assert low == pytest.approx(0.0, abs=0.1) and high == pytest.approx(60.0, abs=0.1)
    loft = loft_scan(posed, faces, axis, 5.0, 55.0, 12)
    check = check_solid(loft.solid.shape)
    assert check.valid
    exact = tube_volume(5.0, 55.0)
    assert abs(check.volume - exact) / exact < 2e-3


def test_sections_outside_the_scan_fail_with_their_position() -> None:
    vertices, faces = tube()
    with pytest.raises(KernelError) as raised:
        loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 10.0, 70.0, 5)
    assert raised.value.code == ErrorCode.NO_SECTION
    assert raised.value.params["position"] == pytest.approx(70.0)


def test_an_empty_range_is_rejected() -> None:
    vertices, faces = tube()
    with pytest.raises(KernelError) as raised:
        loft_scan(vertices, faces, LoftAxis(np.zeros(3), Z), 20.0, 20.0, 5)
    assert raised.value.code == ErrorCode.INVALID_RANGE
