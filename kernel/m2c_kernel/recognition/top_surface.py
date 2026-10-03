"""The top of a feature as heights over its base plane: a plane or a gentle quadric.

Flat and inclined tops are planes. The arms of a direction pad slope down towards its
centre on a cone around the pad's axis: over one arm a plane misses the scan by 0.2 mm
and more at the arm's ends, while a quadric h = c0 + c1 x + c2 y + c3 x^2 + c4 x y +
c5 y^2 (x, y from the top's centre) follows it within the noise. Domed tops are quadrics
as well. Fits weigh the scan triangles by their area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from m2c_kernel.geometry import FloatArray


@dataclass(frozen=True)
class TopSurface:
    """Heights h(u, v) of a top over the base plane (plane frame, mm)."""

    centre: tuple[float, float]
    coefficients: tuple[float, float, float, float, float, float]
    """c0 ... c5 of c0 + c1 x + c2 y + c3 x^2 + c4 x y + c5 y^2, x and y from `centre`."""

    @property
    def planar(self) -> bool:
        return not any(self.coefficients[3:])

    def height(self, uv: FloatArray) -> FloatArray:
        x, y = (np.asarray(uv, dtype=np.float64) - self.centre).T
        c = self.coefficients
        result: FloatArray = c[0] + c[1] * x + c[2] * y + c[3] * x * x + c[4] * x * y + c[5] * y * y
        return result

    def gradient(self, uv: FloatArray) -> FloatArray:
        """(k, 2) rise of the top per mm along u and v."""
        x, y = (np.asarray(uv, dtype=np.float64) - self.centre).T
        c = self.coefficients
        result: FloatArray = np.column_stack(
            [c[1] + 2 * c[3] * x + c[4] * y, c[2] + c[4] * x + 2 * c[5] * y]
        )
        return result

    def tilt(self) -> float:
        """Angle of the top against the base plane at its centre (radians)."""
        return float(np.arctan(np.hypot(self.coefficients[1], self.coefficients[2])))


def fit_top(points: FloatArray, weights: FloatArray, *, quadric: bool) -> TopSurface:
    """The plane (or quadric) of least weighted squared height difference to the points."""
    centre = weights @ points[:, :2]
    x, y = (points[:, :2] - centre).T
    columns = [np.ones(len(points)), x, y]
    if quadric:
        columns += [x * x, x * y, y * y]
    design = np.column_stack(columns)
    root = np.sqrt(weights)
    solution, *_ = np.linalg.lstsq(design * root[:, None], points[:, 2] * root, rcond=None)
    coefficients = [float(value) for value in solution] + [0.0] * (6 - len(solution))
    return TopSurface(
        (float(centre[0]), float(centre[1])),
        (
            coefficients[0],
            coefficients[1],
            coefficients[2],
            coefficients[3],
            coefficients[4],
            coefficients[5],
        ),
    )


def rms(surface: TopSurface, points: FloatArray, weights: FloatArray) -> float:
    """Weighted RMS height difference of the points to the surface."""
    return float(np.sqrt(weights @ (points[:, 2] - surface.height(points[:, :2])) ** 2))
