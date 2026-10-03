"""Planar test profiles built directly with OCCT (the sketch package is not needed)."""

from __future__ import annotations

from typing import Any

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    TopoDS,
    gp_Pnt,
)
from m2c_kernel.cad.profiles import Profile, profile_edges
from m2c_kernel.document.results import PlaneFrame

XY = PlaneFrame(origin=np.zeros(3), x_dir=np.array([1.0, 0, 0]), normal=np.array([0, 0, 1.0]))
XZ = PlaneFrame(origin=np.zeros(3), x_dir=np.array([1.0, 0, 0]), normal=np.array([0, -1.0, 0]))


def _point(frame: PlaneFrame, u: float, v: float) -> gp_Pnt:
    return gp_Pnt(*(frame.origin + u * frame.x_dir + v * frame.y_dir))


def polygon_wire(points: list[tuple[float, float]], frame: PlaneFrame) -> Any:
    maker = BRepBuilderAPI_MakePolygon()
    for u, v in points:
        maker.Add(_point(frame, u, v))
    maker.Close()
    return maker.Wire()


def polygon(points: list[tuple[float, float]], frame: PlaneFrame) -> Any:
    return BRepBuilderAPI_MakeFace(polygon_wire(points, frame), True).Face()


def rectangle_corners(x: float, y: float, width: float, height: float) -> list[tuple[float, float]]:
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]


def rectangle(x: float, y: float, width: float, height: float, frame: PlaneFrame = XY) -> Any:
    """Counter-clockwise rectangle; edge k runs from corner k to corner k + 1."""
    return polygon(rectangle_corners(x, y, width, height), frame)


def rectangle_with_hole(frame: PlaneFrame = XY) -> Any:
    """40 x 20 rectangle with a clockwise 10 x 10 square hole in the middle."""
    maker = BRepBuilderAPI_MakeFace(polygon_wire(rectangle_corners(0, 0, 40, 20), frame), True)
    hole = polygon_wire(list(reversed(rectangle_corners(15, 5, 10, 10))), frame)
    maker.Add(TopoDS.Wire(hole))
    return maker.Face()


def named(face: Any, prefix: str = "e") -> Profile:
    return Profile(face, tuple(f"{prefix}{k}" for k in range(len(profile_edges(face)))))


def rectangle_profile(
    x: float, y: float, width: float, height: float, frame: PlaneFrame = XY
) -> Profile:
    return named(rectangle(x, y, width, height, frame))


def ring_profile() -> Profile:
    """Tube cross-section r = 10..20, h = 30 in the XZ plane (revolve about Z)."""
    return rectangle_profile(10, 0, 10, 30, XZ)
