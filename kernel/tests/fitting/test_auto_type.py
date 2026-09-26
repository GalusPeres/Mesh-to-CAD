"""Automatic type choice: 10 of 10 test patches (ARCHITECTURE.md 1.5)."""

from __future__ import annotations

import numpy as np

from m2c_kernel.fitting.api import FitRequest, run_fit
from tests.fitting.helpers import noisy_patch

# Kind, span around (rad) or width (mm), span along, shape.
PATCHES = [
    ("plane", 40.0, 40.0, {}),
    ("sphere", np.radians(90), np.radians(60), {"radius": 20.0}),
    ("sphere", np.radians(30), np.radians(30), {"radius": 20.0}),
    ("cylinder", np.radians(359), 30.0, {"radius": 12.5}),
    ("cylinder", np.radians(90), 30.0, {"radius": 12.5}),
    ("cylinder", np.radians(45), 10.0, {"radius": 12.5}),
    ("cone", np.radians(359), 20.0, {"half_angle": np.radians(30)}),
    ("cone", np.radians(120), 8.0, {"half_angle": np.radians(45), "apex_distance": 14.0}),
    ("torus", np.radians(359), np.radians(90), {"major_radius": 18.0, "minor_radius": 3.0}),
    ("torus", np.radians(90), np.radians(90), {"major_radius": 18.0, "minor_radius": 3.0}),
]


def test_ten_of_ten_patches_get_the_right_type() -> None:
    chosen = []
    for seed, (kind, span_u, span_v, shape) in enumerate(PATCHES, start=20):
        patch = noisy_patch(kind, span_u, span_v, seed, **shape)
        outcome = run_fit(
            patch.mesh(),
            np.arange(len(patch.faces)),
            FitRequest(kind="auto", snap=False),
            np.random.default_rng(seed),
        )
        chosen.append((kind, outcome.primitive.type))
    assert [truth for truth, _ in chosen] == [fitted for _, fitted in chosen], chosen


def test_alternatives_are_ordered_by_rms_and_include_the_choice() -> None:
    patch = noisy_patch("cylinder", np.radians(120), 20.0, 3, radius=8.0)
    outcome = run_fit(
        patch.mesh(), np.arange(len(patch.faces)), FitRequest(snap=False), np.random.default_rng(3)
    )
    kinds = [alternative.kind for alternative in outcome.alternatives]
    assert kinds[0] == "cylinder" == outcome.primitive.type
    assert {"plane", "sphere"} <= set(kinds)
    rms = [alternative.rms for alternative in outcome.alternatives]
    assert rms == sorted(rms)


def test_an_explicit_kind_is_fitted_even_if_another_fits_better() -> None:
    patch = noisy_patch("cylinder", np.radians(120), 20.0, 4, radius=8.0)
    outcome = run_fit(
        patch.mesh(),
        np.arange(len(patch.faces)),
        FitRequest(kind="plane", snap=False),
        np.random.default_rng(4),
    )
    assert outcome.primitive.type == "plane"
    assert not outcome.stats.passed
    assert outcome.alternatives[0].kind == "cylinder"
