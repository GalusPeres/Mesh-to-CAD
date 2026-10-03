"""A rounded corner in a cross-section: two faces joined by an arc tangent to both.

The faces leave the sharp corner along the unit directions `d1` and `d2` (2-D) and
end at `reach`; the arc of radius r touches both at r / tan(half) from the corner,
where `half` is half the angle between the faces. Every function here evaluates many
candidate corners (position and radius) against the same points at once.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from m2c_kernel.geometry import FloatArray, unit


@dataclass(frozen=True)
class Corner:
    """The two faces of a cross-section, seen from the sharp corner at the origin."""

    d1: FloatArray
    d2: FloatArray
    reach: float

    @property
    def half(self) -> float:
        return float(np.arccos(np.clip(self.d1 @ self.d2, -1.0, 1.0))) / 2.0

    def shifted(self, offsets: FloatArray) -> FloatArray:
        """Where the corner moves when face i moves by offsets[:, i] across itself: (m, 2)."""
        normals = np.array([[-self.d1[1], self.d1[0]], [-self.d2[1], self.d2[0]]])
        result: FloatArray = np.linalg.solve(normals, np.atleast_2d(offsets).T).T
        return result

    def tangent_length(self, radius: float) -> float:
        return radius / float(np.tan(self.half))

    def distances(self, points: FloatArray, corners: FloatArray, radii: FloatArray) -> FloatArray:
        """Distance of every point (k, 2) to every candidate (m corners, m radii): (m, k)."""
        local = points[None, :, :] - corners[:, None, :]
        squared = np.einsum("mki,mki->mk", local, local)
        tangent_length = radii[:, None] / np.tan(self.half)
        along = [local @ self.d1, local @ self.d2]
        nearest = np.full(squared.shape, np.inf)
        for a in along:
            # The face from its tangent point to the reach: the part along it beyond
            # either end, and the part across it.
            s = np.clip(a, tangent_length, self.reach)
            across = np.maximum(squared - a**2, 0.0)
            nearest = np.minimum(nearest, np.sqrt((a - s) ** 2 + across))
        centre = (radii / np.sin(self.half))[:, None]
        along_bisector = local @ unit(self.d1 + self.d2)
        to_centre = np.sqrt(np.maximum(squared - 2.0 * centre * along_bisector + centre**2, 0.0))
        on_arc = (along[0] <= tangent_length) & (along[1] <= tangent_length)
        result: FloatArray = np.where(
            on_arc, np.minimum(nearest, np.abs(to_centre - radii[:, None])), nearest
        )
        return result

    def costs(
        self, points: FloatArray, corners: FloatArray, radii: FloatArray, cap: float
    ) -> FloatArray:
        """Capped squared distance of the points to each candidate: (m,)."""
        result: FloatArray = np.minimum(self.distances(points, corners, radii) ** 2, cap**2).sum(
            axis=1
        )
        return result
