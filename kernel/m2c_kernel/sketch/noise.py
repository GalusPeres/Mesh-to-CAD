"""The noise of a section and the fit tolerance that follows from it.

The local noise is the scatter of the cut over short stretches (median RMS of local
line fits, research 1.3). Scanner software smooths its meshes, so a moulded or
printed part can stray from its designed shape far more than that: the long side
of the remote control scatters by 0.002 mm locally but waves by 0.05 mm along its
length, and a fit at six times the local noise splits it into pieces. Like the
design noise of recognition (the largest plane's RMS), a section's noise is at
least how far its long straight sides stray from their lines (the median over the
sides that span a good part of their loop, at most `MAX_DESIGN_NOISE_MM`). Sections
without a long straight side keep their local noise.
"""

from __future__ import annotations

import math

import numpy as np

from m2c_kernel.sketch import fit2d, split2d
from m2c_kernel.sketch.model import FloatArray
from m2c_kernel.sketch.section import Section

MIN_TOLERANCE = 0.05
NOISE_FACTOR = 6.0
"""Tolerance = 6 sigma: the largest of ~2000 Gaussian residuals stays inside (research 1.3)."""
LONG_SIDE_SHARE = 0.1
"""Straight sides spanning this share of their loop or chain show the design noise..."""
SIDE_TRIM = 0.1
"""...measured without this share of their samples at either end."""
MAX_DESIGN_NOISE_MM = 0.05
"""The design noise is at most this: more would hide small designed steps."""
SIDE_CANDIDATES = 200
"""Breakpoint candidates of the split that finds the sides (coarse is enough)."""


def suggested_tolerance(noise: float) -> float:
    return max(NOISE_FACTOR * noise, MIN_TOLERANCE)


def sample_spacing(raw: FloatArray, closed: bool) -> float:
    """Median raw edge length, clipped to 0.05-1 mm (resampling finer adds no information)."""
    path = np.vstack([raw, raw[:1]]) if closed else raw
    edges = np.linalg.norm(np.diff(path, axis=0), axis=1)
    return float(np.clip(np.median(edges), 0.05, 1.0))


def local_noise(section: Section) -> float:
    """Robust noise sigma pooled over the raw section polylines (not resampled ones)."""
    estimates = [
        (fit2d.estimate_noise(p, closed=True), len(p)) for p in section.loops if len(p) >= 9
    ] + [(fit2d.estimate_noise(p, closed=False), len(p)) for p in section.chains if len(p) >= 9]
    if not estimates:
        return 0.0
    values = np.array([e for e, _ in estimates])
    weights = np.array([n for _, n in estimates], dtype=np.float64)
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def section_noise(section: Section) -> float:
    """The local noise, or the scatter of the long straight sides when that is larger."""
    noise = local_noise(section)
    side = _straightness(section, suggested_tolerance(noise))
    return max(noise, min(side, MAX_DESIGN_NOISE_MM))


def _straightness(section: Section, tolerance: float) -> float:
    """Median scatter of the long straight sides about their lines (0 without one).

    Each side is measured on its inner part: the split may run a side into the
    rounding of its corners, which only touches its ends.
    """
    scatters: list[float] = []
    polylines = [(p, True) for p in section.loops] + [(p, False) for p in section.chains]
    options = fit2d.SegmentOptions(tolerance=tolerance)
    for raw, closed in polylines:
        if len(raw) < 9:
            continue
        spacing = sample_spacing(raw, closed)
        samples = fit2d.resample(raw, spacing, closed)
        points, segments = split2d.split_polyline(
            samples, closed, tolerance / 3.0, spacing, options, max_candidates=SIDE_CANDIDATES
        )
        for segment in segments:
            count = segment.end - segment.start + 1
            if not isinstance(segment.fit, fit2d.LineFit) or count < LONG_SIDE_SHARE * len(samples):
                continue
            trim = int(SIDE_TRIM * count)
            inner = points[segment.start + trim : segment.end - trim + 1]
            scatters.append(math.sqrt(fit2d.fit_line(inner).sse / len(inner)))
    return float(np.median(scatters)) if scatters else 0.0
