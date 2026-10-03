"""Deviation statistics: summary, histogram and per-face numbers.

Only points with a result count (NaN marks points beyond the search distance and
points of synthetic triangles). Values outside the histogram range are clipped into
the outer bins, so the counts stay consistent with the percentages
(`.work/research/algorithms-cad.md` 4.4). Empty sets give None, which travels as null.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

HISTOGRAM_BINS = 41
PASS_SHARE = 0.95
"""The single verdict rule (DESIGN.md 5.3): at least 95 % within the tolerance."""


@dataclass(frozen=True)
class DeviationStats:
    """Statistics of the signed distances of all points with a result (mm; shares 0-1).

    `histogram_counts` covers -`histogram_limit` ... +`histogram_limit` in equal bins;
    `p99_abs` is the 99th percentile of the absolute distance (automatic scale range).
    """

    count: int
    tolerance: float
    mean: float | None
    std: float | None
    rms: float | None
    min: float | None
    max: float | None
    p05: float | None
    p50: float | None
    p95: float | None
    p99_abs: float | None
    within: float | None
    above: float | None
    below: float | None
    passed: bool
    histogram_counts: list[int]
    histogram_limit: float


@dataclass(frozen=True)
class FaceDeviation:
    """Statistics of the points whose closest point lies on one B-Rep face."""

    body: str
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
            count=0, tolerance=tolerance, mean=None, std=None, rms=None, min=None, max=None,
            p05=None, p50=None, p95=None, p99_abs=None, within=None, above=None, below=None,
            passed=False, histogram_counts=[0] * bins, histogram_limit=3.0 * tolerance,
        )  # fmt: skip
    magnitude = np.abs(values)
    p99_abs = float(np.percentile(magnitude, 99))
    limit = max(3.0 * tolerance, float(np.percentile(magnitude, 99.5)))
    counts, _ = np.histogram(np.clip(values, -limit, limit), bins=bins, range=(-limit, limit))
    p05, p50, p95 = np.percentile(values, [5, 50, 95])
    within = float(np.mean(magnitude <= tolerance))
    return DeviationStats(
        count=len(values),
        tolerance=tolerance,
        mean=float(values.mean()),
        std=float(values.std()),
        rms=float(np.sqrt(np.mean(values**2))),
        min=float(values.min()),
        max=float(values.max()),
        p05=float(p05),
        p50=float(p50),
        p95=float(p95),
        p99_abs=p99_abs,
        within=within,
        above=float(np.mean(values > tolerance)),
        below=float(np.mean(values < -tolerance)),
        passed=within >= PASS_SHARE,
        histogram_counts=[int(count) for count in counts],
        histogram_limit=limit,
    )


def per_face_stats(
    signed: npt.ArrayLike,
    global_face: npt.ArrayLike,
    tolerance: float,
    body_face: Callable[[int], tuple[str, int]],
) -> list[FaceDeviation]:
    """Statistics per B-Rep face; `body_face` turns a global face index into (body, face)."""
    values = np.asarray(signed, dtype=np.float64)
    faces = np.asarray(global_face, dtype=np.int64)
    valid = np.isfinite(values) & (faces >= 0)
    values, faces = values[valid], faces[valid]
    if len(values) == 0:
        return []
    ids, inverse, counts = np.unique(faces, return_inverse=True, return_counts=True)
    total = np.bincount(inverse, weights=values)
    squares = np.bincount(inverse, weights=values**2)
    inside = np.bincount(inverse, weights=(np.abs(values) <= tolerance).astype(np.float64))
    max_abs = np.zeros(len(ids))
    np.maximum.at(max_abs, inverse, np.abs(values))
    result = []
    for i, face_id in enumerate(ids):
        body, face = body_face(int(face_id))
        result.append(
            FaceDeviation(
                body=body,
                face=face,
                count=int(counts[i]),
                mean=float(total[i] / counts[i]),
                rms=float(np.sqrt(squares[i] / counts[i])),
                max_abs=float(max_abs[i]),
                within=float(inside[i] / counts[i]),
            )
        )
    return result
