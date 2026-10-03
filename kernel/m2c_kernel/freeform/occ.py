"""Open CASCADE objects of the freeform package: B-spline patch faces and lofts.

The OCP names below are not exported by `cad/occ_compat.py` yet (interface request
T4, `.work/interface-requests/T4.md`); they are imported in this one module so the
move to `occ_compat` touches a single import block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.collections import (
    Array1_double,
    Array1_int,
    Array2_gp_Pnt,
    HArray1_double,
    HArray1_gp_Pnt,
)
from OCP.Geom import Geom_BSplineSurface
from OCP.GeomAPI import GeomAPI_Interpolate

from m2c_kernel.cad.occ_compat import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepCheck_Analyzer,
    Standard_Failure,
    TopAbs_EDGE,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    indexed_map,
)
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.heightfield import DEGREE, HeightField
from m2c_kernel.geometry import FloatArray
from m2c_kernel.protocol.errors import KernelError

FACE_TOLERANCE_MM = 1e-6
INTERPOLATION_TOLERANCE_MM = 1e-6


def bspline_surface(surface: HeightField) -> Geom_BSplineSurface:
    """The height field as an exact Open CASCADE B-spline surface."""
    poles = surface.poles()
    nu, nv, _ = poles.shape
    grid = Array2_gp_Pnt(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            grid.SetValue(i + 1, j + 1, gp_Pnt(*(float(value) for value in poles[i, j])))
    knots_u, mults_u = _knots(surface.knots_u)
    knots_v, mults_v = _knots(surface.knots_v)
    return Geom_BSplineSurface(grid, knots_u, knots_v, mults_u, mults_v, DEGREE, DEGREE)


def _knots(knots: FloatArray) -> tuple[Array1_double, Array1_int]:
    values, multiplicities = np.unique(knots, return_counts=True)
    result, counts = Array1_double(1, len(values)), Array1_int(1, len(values))
    for index, (value, multiplicity) in enumerate(zip(values, multiplicities, strict=True), 1):
        result.SetValue(index, float(value))
        counts.SetValue(index, int(multiplicity))
    return result, counts


def patch_face(surface: HeightField) -> TopoDS_Shape:
    """A face over the full parameter rectangle of the patch; fails if it is not valid."""
    try:
        maker = BRepBuilderAPI_MakeFace(bspline_surface(surface), FACE_TOLERANCE_MM)
        face = maker.Face() if maker.IsDone() else None
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.INVALID_SURFACE, details=str(failure)) from None
    if face is None or not BRepCheck_Analyzer(face).IsValid():
        raise KernelError(ErrorCode.INVALID_SURFACE)
    return face


def section_wire(points: FloatArray) -> TopoDS_Shape:
    """A closed wire of one periodic B-spline through the section points.

    The points are evenly spaced along the section (`normalise_section`), so they get
    evenly spaced parameters. With chord-length parameters instead, every section of a
    scan gets knots of its own, the loft through them carries all of them (on a remote
    control: 1,522 knots around the wall), and no fillet runs along its end edge.
    """
    count = len(points)
    array = HArray1_gp_Pnt(1, count)
    for index, point in enumerate(points, start=1):
        array.SetValue(index, gp_Pnt(*(float(value) for value in point)))
    # A periodic interpolation takes one parameter more than points: the closing one.
    parameters = HArray1_double(1, count + 1)
    for index in range(count + 1):
        parameters.SetValue(index + 1, index / count)
    try:
        interpolation = GeomAPI_Interpolate(array, parameters, True, INTERPOLATION_TOLERANCE_MM)
        interpolation.Perform()
        done = interpolation.IsDone()
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.LOFT_FAILED, details=str(failure)) from None
    if not done:
        raise KernelError(ErrorCode.LOFT_FAILED)
    edge = BRepBuilderAPI_MakeEdge(interpolation.Curve()).Edge()
    return BRepBuilderAPI_MakeWire(edge).Wire()


@dataclass(frozen=True)
class LoftShape:
    shape: TopoDS_Shape
    start_cap: TopoDS_Shape
    end_cap: TopoDS_Shape
    lateral: tuple[Any, ...]
    """Lateral faces, in the order of the edges of the first section."""


def thru_sections(wires: list[TopoDS_Shape]) -> LoftShape:
    """A smooth (not ruled) solid through the section wires."""
    maker = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    maker.CheckCompatibility(True)
    for wire in wires:
        maker.AddWire(TopoDS.Wire(wire))
    try:
        maker.Build()
        done = maker.IsDone()
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.LOFT_FAILED, details=str(failure)) from None
    if not done:
        raise KernelError(ErrorCode.LOFT_FAILED)
    edges = indexed_map(wires[0], TopAbs_EDGE)
    lateral = tuple(
        maker.GeneratedFace(edges.FindKey(index)) for index in range(1, edges.Extent() + 1)
    )
    return LoftShape(maker.Shape(), maker.FirstShape(), maker.LastShape(), lateral)
