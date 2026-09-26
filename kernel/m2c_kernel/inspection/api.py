"""Public API of the deviation analysis.

Sign convention: a positive distance means the scan point lies outside the
body (excess material on the real part), negative means inside.

Not implemented yet. Method: seeded vertex-ring descent with per-face walkers,
B-Rep edge seeds and pseudo-normal signs on a reference tessellation with
linear deflection at most tolerance / 20. Measurements:
`.work/research/algorithms-cad.md` section 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray

if TYPE_CHECKING:
    from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class SignedDistances:
    """Distance per point (NaN beyond the search distance) and the B-Rep face hit."""

    distances: npt.NDArray[np.float32]
    face_ids: npt.NDArray[np.int32]


def signed_distances(
    points: FloatArray, bodies: list[Body], max_distance: float, tolerance: float, job: JobContext
) -> SignedDistances:
    """Signed distances from scan points to the nearest body surface."""
    raise NotImplementedError("deviation analysis")
