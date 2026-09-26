"""The single entry point to Open CASCADE (OCP 8.0).

Other kernel modules import OCP names from here, so differences between OCP
versions are handled in one place. OCP 8 specifics that break older examples:

- Collections live in `OCP.collections` (`List_TopoDS_Shape`,
  `IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher`, ...).
- Down-casts are module functions without suffix (`TopoDS.Face(shape)`); static
  class methods keep the `_s` suffix (`TopExp.MapShapes_s`).
- Boolean error reports, `BRepCheck_Result.Status()` and `Bnd_Box.Get()` are not
  bound. Progress indicators cannot be subclassed, so long OCCT calls can neither
  report progress nor be cancelled (see `JobContext.native`).
- `write.step.*` parameters exist only after `STEPControl_Controller.Init_s()`.
- `BRepMesh_IncrementalMesh` keeps a finer existing triangulation; call
  `BRepTools.Clean_s` first when a specific density is needed.

Details: `.work/research/algorithms-cad.md` section 0.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import (
    BRepAlgoAPI_Common,
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepAlgoAPI_Splitter,
)
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeHalfSpace,
    BRepPrimAPI_MakePrism,
    BRepPrimAPI_MakeRevol,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
)
from OCP.BRepTools import BRepTools
from OCP.collections import (
    IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as EdgeFaceMap,
)
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.collections import List_TopoDS_Shape
from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import (
    gp_Ax1,
    gp_Ax2,
    gp_Ax3,
    gp_Circ,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Pnt2d,
    gp_Trsf,
    gp_Vec,
)
from OCP.GProp import GProp_GProps
from OCP.Message import Message, Message_Gravity
from OCP.ShapeFix import ShapeFix_Shape
from OCP.Standard import Standard_Failure
from OCP.StdFail import StdFail_NotDone
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_REVERSED,
    TopAbs_ShapeEnum,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape

__all__ = [
    "BRepAdaptor_Curve",
    "BRepAdaptor_Surface",
    "BRepAlgoAPI_Common",
    "BRepAlgoAPI_Cut",
    "BRepAlgoAPI_Fuse",
    "BRepAlgoAPI_Splitter",
    "BRepBndLib",
    "BRepBuilderAPI_MakeEdge",
    "BRepBuilderAPI_MakeFace",
    "BRepBuilderAPI_MakePolygon",
    "BRepBuilderAPI_MakeVertex",
    "BRepBuilderAPI_MakeWire",
    "BRepBuilderAPI_Transform",
    "BRepCheck_Analyzer",
    "BRepClass_FaceClassifier",
    "BRepExtrema_DistShapeShape",
    "BRepFilletAPI_MakeChamfer",
    "BRepFilletAPI_MakeFillet",
    "BRepGProp",
    "BRepMesh_IncrementalMesh",
    "BRepPrimAPI_MakeBox",
    "BRepPrimAPI_MakeCone",
    "BRepPrimAPI_MakeCylinder",
    "BRepPrimAPI_MakeHalfSpace",
    "BRepPrimAPI_MakePrism",
    "BRepPrimAPI_MakeRevol",
    "BRepPrimAPI_MakeSphere",
    "BRepPrimAPI_MakeTorus",
    "BRepTools",
    "BRep_Tool",
    "Bnd_Box",
    "EdgeFaceMap",
    "GC_MakeArcOfCircle",
    "GC_MakeSegment",
    "GProp_GProps",
    "GeomAPI_ProjectPointOnSurf",
    "GeomAbs_Plane",
    "List_TopoDS_Shape",
    "ShapeFix_Shape",
    "ShapeMap",
    "Standard_Failure",
    "StdFail_NotDone",
    "TopAbs_EDGE",
    "TopAbs_FACE",
    "TopAbs_IN",
    "TopAbs_REVERSED",
    "TopAbs_SOLID",
    "TopAbs_ShapeEnum",
    "TopAbs_VERTEX",
    "TopExp",
    "TopExp_Explorer",
    "TopLoc_Location",
    "TopoDS",
    "TopoDS_Face",
    "TopoDS_Shape",
    "gp_Ax1",
    "gp_Ax2",
    "gp_Ax3",
    "gp_Circ",
    "gp_Dir",
    "gp_Pln",
    "gp_Pnt",
    "gp_Pnt2d",
    "gp_Trsf",
    "gp_Vec",
    "indexed_map",
    "occt_version",
    "quiet_occt",
]


def indexed_map(shape: TopoDS_Shape, kind: TopAbs_ShapeEnum) -> ShapeMap:
    """Sub-shapes of one type in a stable order (valid for this shape object only)."""
    shape_map = ShapeMap()
    TopExp.MapShapes_s(shape, kind, shape_map)
    return shape_map


def quiet_occt() -> None:
    """Silence OCCT's default console printer (it writes transfer statistics to stdout)."""
    printers = Message.DefaultMessenger_s().Printers()
    for index in range(1, printers.Size() + 1):
        printers.Value(index).SetTraceLevel(Message_Gravity.Message_Fail)


@cache
def occt_version() -> str:
    """Open CASCADE version, read from the version resource of the TKernel DLL.

    OCP 8 has no `Standard_Version` binding, so the API cannot report it.
    """
    import OCP

    libs = Path(OCP.__file__).resolve().parents[1] / "cadquery_ocp.libs"
    dll = next(libs.glob("TKernel*.dll"), None)
    if dll is None:
        return "unknown"
    pattern = rb"F\x00i\x00l\x00e\x00V\x00e\x00r\x00s\x00i\x00o\x00n\x00\x00\x00+((?:[0-9.]\x00)+)"
    match = re.search(pattern, dll.read_bytes())
    return match.group(1).decode("utf-16-le") if match else "unknown"


def ocp_version() -> str:
    import OCP

    return str(getattr(OCP, "__version__", "unknown"))
