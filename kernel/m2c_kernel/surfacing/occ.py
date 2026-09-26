"""Open CASCADE names the surfacing package needs beyond `cad.occ_compat`.

`cad/occ_compat.py` is the kernel's single OCP entry point, but it does not export the
B-spline, B-Rep builder and shell-fixing classes used here yet. They are imported in
this one module until they are added there (interface request T10).
"""

from __future__ import annotations

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepLib import BRepLib
from OCP.collections import Array1_double, Array1_gp_Pnt, Array1_int, Array2_gp_Pnt
from OCP.Geom import Geom_BSplineCurve, Geom_BSplineSurface
from OCP.Geom2d import Geom2d_Line
from OCP.gp import gp_Dir2d, gp_Pnt2d
from OCP.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED
from OCP.TopoDS import TopoDS_Face, TopoDS_Shell, TopoDS_Solid, TopoDS_Vertex, TopoDS_Wire

__all__ = [
    "Array1_double",
    "Array1_gp_Pnt",
    "Array1_int",
    "Array2_gp_Pnt",
    "BRepBuilderAPI_MakeEdge",
    "BRepLib",
    "BRep_Builder",
    "Geom2d_Line",
    "Geom_BSplineCurve",
    "Geom_BSplineSurface",
    "TopAbs_FORWARD",
    "TopAbs_REVERSED",
    "TopoDS_Face",
    "TopoDS_Shell",
    "TopoDS_Solid",
    "TopoDS_Vertex",
    "TopoDS_Wire",
    "gp_Dir2d",
    "gp_Pnt2d",
]
