"""Public API of freeform patches and lofts.

Not implemented yet. The patch is a P-spline height field converted exactly to
a `Geom_BSplineSurface`; the loft runs `BRepOffsetAPI_ThruSections` through
normalised periodic sections. Methods and measurements:
`.work/research/algorithms-cad.md` section 3.
"""

from __future__ import annotations

from typing import Any

from m2c_kernel.geometry import FloatArray


def fit_height_field(
    points: FloatArray, spans: tuple[int, int] | None, smoothing: float, margin: float
) -> Any:
    """Fit a B-spline surface to points whose normals share one hemisphere."""
    raise NotImplementedError("freeform patches")


def loft_sections(sections: list[FloatArray]) -> Any:
    """A solid through closed planar sections."""
    raise NotImplementedError("lofts")
