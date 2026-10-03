"""Volume and area of bodies.

Without a precision, Open CASCADE integrates every face with a fixed number of Gauss
points. That is exact enough on planes, cylinders and the like, but not on B-spline
faces with many knots: a short loft came out 3.7 % low, a filleted remote control 7 %
high. With a precision, the integration follows the knots and is exact, and its time
grows with them: 0.1 s for the remote's lofted wall, 25 s once a fillet along that
wall trims it (the fillet face has 15,000 poles). Bodies with faces or edges that
large take their volume and area from the display triangulation instead: 0.4 s and
within 0.1 % on the remote.
"""

from __future__ import annotations

from typing import Literal

from m2c_kernel.cad.deflection import DISPLAY_ANGULAR_DEFLECTION_RAD, DISPLAY_LINEAR_DEFLECTION_MM
from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Curve,
    BRepAdaptor_Surface,
    BRepGProp,
    BRepMesh_IncrementalMesh,
    GeomAbs_BSplineCurve,
    GeomAbs_BSplineSurface,
    GProp_GProps,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopoDS,
    TopoDS_Shape,
    indexed_map,
)

type Method = Literal["gauss", "precise", "mesh"]

PRECISION = 1e-4
"""Relative precision of the integration where it follows the knots."""
MAX_POLES = 4096
"""Largest pole count of a face or edge (in one direction) integrated precisely."""


def volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    match _method(shape):
        case "gauss":
            BRepGProp.VolumeProperties_s(shape, props)
        case "precise":
            BRepGProp.VolumeProperties_s(shape, props, PRECISION)
        case "mesh":
            BRepGProp.VolumeProperties_s(shape, props, False, False, True)
    return float(props.Mass())


def area(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    match _method(shape):
        case "gauss":
            BRepGProp.SurfaceProperties_s(shape, props)
        case "precise":
            BRepGProp.SurfaceProperties_s(shape, props, PRECISION)
        case "mesh":
            BRepGProp.SurfaceProperties_s(shape, props, False, True)
    return float(props.Mass())


def _method(shape: TopoDS_Shape) -> Method:
    largest = 0
    faces = indexed_map(shape, TopAbs_FACE)
    for index in range(1, faces.Extent() + 1):
        surface = BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(index)))
        if surface.GetType() == GeomAbs_BSplineSurface:
            largest = max(largest, surface.NbUPoles(), surface.NbVPoles(), 1)
    if largest == 0:
        return "gauss"
    edges = indexed_map(shape, TopAbs_EDGE)
    for index in range(1, edges.Extent() + 1):
        curve = BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(index)))
        if curve.GetType() == GeomAbs_BSplineCurve:
            largest = max(largest, curve.NbPoles())
    if largest <= MAX_POLES:
        return "precise"
    # The same triangulation the display uses, so it is made only once.
    BRepMesh_IncrementalMesh(
        shape, DISPLAY_LINEAR_DEFLECTION_MM, False, DISPLAY_ANGULAR_DEFLECTION_RAD, True
    )
    return "mesh"
