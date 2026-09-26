"""Planar test profiles built directly with OCCT (the sketch package is not needed)."""

from __future__ import annotations

from typing import Any

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    gp_Pnt,
)
from m2c_kernel.cad.solids import Profile, profile_edges
from m2c_kernel.document.results import PlaneFrame

XY = PlaneFrame(origin=np.zeros(3), x_dir=np.array([1.0, 0, 0]), normal=np.array([0, 0, 1.0]))
XZ = PlaneFrame(origin=np.zeros(3), x_dir=np.array([1.0, 0, 0]), normal=np.array([0, -1.0, 0]))


def polygon(points: list[tuple[float, float]], frame: PlaneFrame) -> Any:
    maker = BRepBuilderAPI_MakePolygon()
    for u, v in points:
        maker.Add(gp_Pnt(*(frame.origin + u * frame.x_dir + v * frame.y_dir)))
    maker.Close()
    return BRepBuilderAPI_MakeFace(maker.Wire(), True).Face()


def rectangle(x: float, y: float, width: float, height: float, frame: PlaneFrame = XY) -> Any:
    """Counter-clockwise rectangle; edge k runs from corner k to corner k + 1."""
    corners = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    return polygon(corners, frame)


def named(face: Any) -> Profile:
    return Profile(face, tuple(f"e{k}" for k in range(len(profile_edges(face)))))


def rectangle_profile(
    x: float, y: float, width: float, height: float, frame: PlaneFrame = XY
) -> Profile:
    return named(rectangle(x, y, width, height, frame))


def ring_profile() -> Profile:
    """Tube cross-section r = 10..20, h = 30 in the XZ plane (revolve about Z)."""
    return rectangle_profile(10, 0, 10, 30, XZ)
