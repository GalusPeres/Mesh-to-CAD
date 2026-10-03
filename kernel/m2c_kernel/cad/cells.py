"""Pieces of bodies, open surfaces and planes cut by each other ("Zuschneiden").

All inputs are intersected with each other at once (`BOPAlgo_MakerVolume`, the
general fuse that builds solids from faces): every closed region their faces bound
becomes a cell. A plane enters as a rectangle that reaches past everything else, so
a net pushed past two planes and the planes enclose one cell. The caller decides
which cells form the result and fuses them (`cad.booleans.fuse_all`).

Face tags: faces of input bodies keep theirs (through the builder's history),
pieces of a surface are tagged `<surface tag>:face`, pieces of a plane
`<plane tag>:cap`, anything else `<tag>:piece`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.cad.booleans import FUZZY_VALUE_MM
from m2c_kernel.cad.occ_compat import (
    Bnd_Box,
    BOPAlgo_MakerVolume,
    BRep_Tool,
    BRepAdaptor_Surface,
    BRepBndLib,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeVertex,
    BRepClass3d_SolidClassifier,
    BRepExtrema_DistShapeShape,
    BRepGProp,
    GeomAPI_ProjectPointOnSurf,
    GProp_GProps,
    List_TopoDS_Shape,
    Standard_Failure,
    TopAbs_IN,
    TopAbs_REVERSED,
    TopAbs_SOLID,
    TopoDS,
    TopoDS_Shape,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Vec,
    indexed_map,
)
from m2c_kernel.cad.tags import TagCollector, faces_of, point_on_face
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

PLANE_REACH = 1.5
"""A plane's rectangle spans this many times the diagonal of the other inputs."""
_PROBE_FACES = 4
"""Largest faces of a cell from which interior points are looked for."""


@dataclass(frozen=True)
class SurfaceInput:
    """An open surface (a shell, face or compound of faces) and the tag of its faces."""

    shape: TopoDS_Shape
    tag: str


@dataclass(frozen=True)
class PlaneInput:
    origin: FloatArray
    normal: FloatArray
    tag: str


@dataclass(frozen=True)
class Cell:
    body: Body
    volume: float
    probes: FloatArray
    """(k, 3) points inside the cell, deepest first (may be empty for degenerate cells)."""


def split_cells(
    bodies: Sequence[Body],
    surfaces: Sequence[SurfaceInput],
    planes: Sequence[PlaneInput],
    tag: str,
) -> list[Cell]:
    """Every closed region the inputs' faces bound, as a tagged solid."""
    shapes = [body.shape for body in bodies] + [surface.shape for surface in surfaces]
    plane_faces = [_plane_face(plane, shapes) for plane in planes]
    arguments = List_TopoDS_Shape()
    for shape in [*shapes, *plane_faces]:
        arguments.Append(shape)
    maker = BOPAlgo_MakerVolume()
    maker.SetArguments(arguments)
    maker.SetFuzzyValue(FUZZY_VALUE_MM)
    maker.SetNonDestructive(True)
    maker.SetRunParallel(False)
    try:
        maker.Perform()
        failed = maker.HasErrors()
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": "trim"}, str(failure)) from None
    if failed:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": "trim"})

    solids = indexed_map(maker.Shape(), TopAbs_SOLID)
    cells = []
    for index in range(1, solids.Extent() + 1):
        solid = solids.FindKey(index)
        collector = TagCollector(solid)
        for body in bodies:
            collector.carry(maker, body)
        for surface in surfaces:
            _tag_pieces(collector, maker, surface.shape, f"{surface.tag}:face")
        for plane, face in zip(planes, plane_faces, strict=True):
            _tag_pieces(collector, maker, face, f"{plane.tag}:cap")
        for missing in collector.missing():
            collector.set(collector.face(missing), f"{tag}:piece")
        volume, area = _measure(solid)
        if volume <= 0.0:
            continue
        cells.append(Cell(collector.body(), volume, interior_points(solid, volume, area)))
    return cells


def interior_points(solid: TopoDS_Shape, volume: float, area: float) -> FloatArray:
    """Points inside the solid, stepped in from its largest faces.

    The step is the solid's volume over its area: half the thickness of a slab and
    about half the inscribed radius of a thin wedge, so the points sit well inside
    even thin pieces and away from the faces (which may lie on the scan).
    """
    depth = volume / max(area, 1e-12)
    faces = faces_of(solid)
    by_area = sorted(
        (faces.FindKey(index) for index in range(1, faces.Extent() + 1)),
        key=lambda face: -_measure(face)[1],
    )
    points: list[FloatArray] = []
    for face in by_area[:_PROBE_FACES]:
        start, inward = _inward(face)
        for share in (1.0, 0.5, 0.25):
            candidate = start + inward * depth * share
            if _inside(solid, candidate):
                points.append(candidate)
                break
    return np.array(points, dtype=np.float64).reshape(-1, 3)


def distance_to(shape: TopoDS_Shape, point: FloatArray) -> float:
    """Distance of a point to a solid (0 inside it)."""
    if _inside(shape, point):
        return 0.0
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    extrema = BRepExtrema_DistShapeShape(vertex, shape)
    if not extrema.IsDone() or extrema.NbSolution() == 0:
        return float("inf")
    return float(extrema.Value())


def _tag_pieces(collector: TagCollector, maker: object, shape: TopoDS_Shape, tag: str) -> None:
    faces = faces_of(shape)
    for index in range(1, faces.Extent() + 1):
        face = faces.FindKey(index)
        pieces = list(maker.Modified(face))  # type: ignore[attr-defined]
        collector.set_all(pieces or [face], tag)


def _plane_face(plane: PlaneInput, shapes: Sequence[TopoDS_Shape]) -> TopoDS_Shape:
    """A square of the plane, centred where the others are, reaching past all of them."""
    box = Bnd_Box()
    for shape in shapes:
        BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        raise KernelError(ErrorCode.TRIM_NEEDS_SURFACE)
    low = np.array(box.CornerMin().Coord())
    high = np.array(box.CornerMax().Coord())
    normal = unit(plane.normal)
    origin = np.asarray(plane.origin, dtype=np.float64)
    centre = (low + high) / 2
    centre = centre - float((centre - origin) @ normal) * normal
    half = PLANE_REACH * float(np.linalg.norm(high - low)) / 2 + 1.0
    surface = gp_Pln(gp_Pnt(*centre), gp_Dir(*normal))
    return BRepBuilderAPI_MakeFace(surface, -half, half, -half, half).Face()


def _measure(shape: TopoDS_Shape) -> tuple[float, float]:
    """Volume (0 for faces) and area."""
    volume = GProp_GProps()
    area = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, area)
    if shape.ShapeType() == TopAbs_SOLID:
        BRepGProp.VolumeProperties_s(shape, volume)
    return float(volume.Mass()), float(area.Mass())


def _inward(face: TopoDS_Shape) -> tuple[FloatArray, FloatArray]:
    """A point inside the face and the unit normal there pointing into its solid."""
    point = np.array(point_on_face(face), dtype=np.float64)
    typed = TopoDS.Face(face)
    projection = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), BRep_Tool.Surface_s(typed))
    u, v = projection.LowerDistanceParameters()
    foot, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    BRepAdaptor_Surface(typed).D1(u, v, foot, du, dv)
    normal = unit(np.cross(np.array(du.Coord()), np.array(dv.Coord())))
    # A forward face of a solid has its normal outward; the inside is the other way.
    inward = normal if typed.Orientation() == TopAbs_REVERSED else -normal
    return point, inward


def _inside(solid: TopoDS_Shape, point: FloatArray) -> bool:
    classifier = BRepClass3d_SolidClassifier(solid, gp_Pnt(*point), 1e-7)
    return bool(classifier.State() == TopAbs_IN)
