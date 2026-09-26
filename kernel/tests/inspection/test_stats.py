"""Deviation statistics against plain numpy."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.inspection.stats import HISTOGRAM_BINS, deviation_stats, per_face_stats


def _values() -> np.ndarray:
    rng = np.random.default_rng(5)
    values = rng.normal(0.01, 0.05, 100_000)
    values[:300] = rng.uniform(0.3, 1.0, 300)
    values[300:400] = np.nan
    return values.astype(np.float32)


def test_summary_matches_numpy() -> None:
    values = _values()
    stats = deviation_stats(values, tolerance=0.1)
    finite = values[np.isfinite(values)].astype(np.float64)
    assert stats.count == len(finite) == 99_900
    assert stats.mean == pytest.approx(finite.mean(), rel=1e-12)
    assert stats.std == pytest.approx(finite.std(), rel=1e-12)
    assert stats.rms == pytest.approx(np.sqrt(np.mean(finite**2)), rel=1e-12)
    assert stats.min == pytest.approx(finite.min())
    assert stats.max == pytest.approx(finite.max())
    assert [stats.p05, stats.p50, stats.p95] == pytest.approx(
        np.percentile(finite, [5, 50, 95]).tolist()
    )
    assert stats.p99_abs == pytest.approx(np.percentile(np.abs(finite), 99))
    assert stats.within == pytest.approx(np.mean(np.abs(finite) <= 0.1))
    assert stats.above == pytest.approx(np.mean(finite > 0.1))
    assert stats.below == pytest.approx(np.mean(finite < -0.1))
    assert stats.within + stats.above + stats.below == pytest.approx(1.0)
    assert stats.passed == (stats.within >= 0.95)


def test_histogram_keeps_outliers_in_the_outer_bins() -> None:
    stats = deviation_stats(_values(), tolerance=0.1)
    assert len(stats.histogram_counts) == HISTOGRAM_BINS
    assert sum(stats.histogram_counts) == stats.count
    assert stats.histogram_limit >= 0.3
    assert stats.histogram_counts[-1] > 0


def test_verdict_uses_the_95_percent_rule() -> None:
    inside = np.full(95, 0.05)
    outside = np.full(5, 0.5)
    assert deviation_stats(np.concatenate([inside, outside]), 0.1).passed
    assert not deviation_stats(np.concatenate([inside[:-1], outside, [0.5]]), 0.1).passed


def test_an_empty_set_has_no_statistics() -> None:
    stats = deviation_stats(np.full(10, np.nan), tolerance=0.1)
    assert stats.count == 0
    assert stats.mean is None and stats.rms is None and stats.within is None
    assert not stats.passed
    assert sum(stats.histogram_counts) == 0


def test_per_face_statistics_match_a_grouped_computation() -> None:
    values = _values()
    faces = np.random.default_rng(6).integers(0, 7, len(values))
    faces[:50] = -1
    result = per_face_stats(values, faces, 0.1, lambda face: ("f1" if face < 4 else "f2", face))
    assert [item.face for item in result] == list(range(7))
    for item in result:
        rows = (faces == item.face) & np.isfinite(values)
        selected = values[rows].astype(np.float64)
        assert item.body == ("f1" if item.face < 4 else "f2")
        assert item.count == len(selected)
        assert item.mean == pytest.approx(selected.mean())
        assert item.rms == pytest.approx(np.sqrt(np.mean(selected**2)))
        assert item.max_abs == pytest.approx(np.abs(selected).max())
        assert item.within == pytest.approx(np.mean(np.abs(selected) <= 0.1))
