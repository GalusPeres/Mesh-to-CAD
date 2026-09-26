"""Contracts of the shared value snapping used by fits (T2) and sketches (T5)."""

from __future__ import annotations

import pytest

from m2c_kernel.snapping import INCH_MM, snap_angle, snap_length, snap_window


def test_radius_snaps_to_whole_millimetres_inside_the_window() -> None:
    snap = snap_length(7.987, 0.012)
    assert snap is not None
    assert snap.value == pytest.approx(8.0)
    assert snap.step == pytest.approx(1.0)
    assert snap.measured == pytest.approx(7.987)


def test_value_outside_the_window_does_not_snap() -> None:
    # 6.37 +- 0.004: the nearest 0.05 mm step (6.35) is 5 uncertainties away.
    assert snap_length(6.37, 0.004, floor=0.0) is None


def test_coarsest_step_wins() -> None:
    snap = snap_length(99.973, 0.02)
    assert snap is not None
    assert snap.value == pytest.approx(100.0)


def test_preferred_values_come_first() -> None:
    snap = snap_length(4.02, 0.01, preferred=(4.01,))
    assert snap is not None
    assert snap.value == pytest.approx(4.01)
    assert snap.step is None


def test_inch_parts_snap_to_fractions() -> None:
    snap = snap_length(0.5 * INCH_MM + 0.01, 0.01, units="inch")
    assert snap is not None
    assert snap.value == pytest.approx(0.5 * INCH_MM)


def test_angles_snap_to_common_angles_only() -> None:
    snap = snap_angle(89.97, 0.02)
    assert snap is not None and snap.value == 90.0
    assert snap_angle(3.0, 0.02) is None


def test_window_has_a_floor() -> None:
    assert snap_window(0.0, 0.005) == 0.005
    assert snap_window(0.01, 0.005) == pytest.approx(0.03)
