"""Deviation statistics: summary, histogram and per-face numbers.

Values outside the histogram range are clipped into the outer bins, so the counts
stay consistent with the percentages (`.work/research/algorithms-cad.md` 4.4).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

HISTOGRAM_BINS = 41


@dataclass(frozen=True)
class DeviationStats:
    """Statistics of the signed distances of all points with a result (mm, fractions 0-1)."""

    count: int
    mean: float
    std: float
    rms: float
    min: float
    max: float
    p05: float
    p50: float
    p95: float
    within: float
    above: float
    below: float
    histogram_counts: list[int]
    histogram_limit: float
    """Bins cover -limit ... +limit evenly; outliers are counted in the outer bins."""


@dataclass(frozen=True)
class FaceDeviation:
    """Statistics of the points whose closest point lies on one B-Rep face."""

    body_id: str
    face: int
    count: int
    mean: float
    rms: float
    max_abs: float
    within: float


def deviation_stats(
    signed: npt.ArrayLike, tolerance: float, bins: int = HISTOGRAM_BINS
) -> DeviationStats:
    values = np.asarray(signed, dtype=np.float64)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return DeviationStats(
            count=0, mean=0.0, std=0.0, rms=0.0, min=0.0, max=0.0, p05=0.0, p50=0.0, p95=0.0,
            within=0.0, above=0.0, below=0.0, histogram_counts=[0] * bins,
            histogram_limit=3.0 * tolerance,
        )  # fmt: skip
    limit = max(3.0 * tolerance, float(np.percentile(np.abs(values), 99.5)))
    counts, _ = np.histogram(np.clip(values, -limit, limit), bins=bins, range=(-limit, limit))
    p05, p50, p95 = np.percentile(values, [5, 50, 95])
    return DeviationStats(
        count=len(values),
        mean=float(values.mean()),
        std=float(values.std()),
        rms=float(np.sqrt(np.mean(values**2))),
        min=float(values.min()),
        max=float(values.max()),
        p05=float(p05),
        p50=float(p50),
        p95=float(p95),
        within=float(np.mean(np.abs(values) <= tolerance)),
        above=float(np.mean(values > tolerance)),
        below=float(np.mean(values < -tolerance)),
        histogram_counts=[int(count) for count in counts],
        histogram_limit=limit,
    )


def per_face_stats(
    signed: npt.ArrayLike, face: npt.ArrayLike, tolerance: float
) -> list[tuple[int, int, float, float, float, float]]:
    """(global face, count, mean, rms, max |d|, fraction within) per face with results."""
    values = np.asarray(signed, dtype=np.float64)
    faces = np.asarray(face, dtype=np.int64)
    valid = np.isfinite(values)
    values, faces = values[valid], faces[valid]
    if len(values) == 0:
        return []
    ids, inverse, counts = np.unique(faces, return_inverse=True, return_counts=True)
    total = np.bincount(inverse, weights=values)
    squares = np.bincount(inverse, weights=values**2)
    inside = np.bincount(inverse, weights=(np.abs(values) <= tolerance).astype(np.float64))
    max_abs = np.zeros(len(ids))
    np.maximum.at(max_abs, inverse, np.abs(values))
    return [
        (
            int(ids[i]),
            int(counts[i]),
            float(total[i] / counts[i]),
            float(np.sqrt(squares[i] / counts[i])),
            float(max_abs[i]),
            float(inside[i] / counts[i]),
        )
        for i in range(len(ids))
    ]
