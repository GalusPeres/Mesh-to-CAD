"""Write the example scans that ship with Mesh-to-CAD into resources/examples/.

The examples are generated, not scanned, so they can be redistributed with the
application under its MIT licence. Each part is modelled with Open CASCADE,
tessellated finely, subdivided to an even triangle size like a scanner mesh
(at most 300,000 triangles), displaced along the normals with Gaussian noise
(sigma 0.03 mm) and placed in a tilted pose, so aligning is part of the work.

    .venv/Scripts/python scripts/generate-examples.py

- bracket: L-shaped bracket, 80 x 50 x 60 mm, fillets, two D9 holes in the base and
  a D12 hole in the upright (the getting-started guide walks through this one).
- flange: D100 flange with a D50 hub, D30 bore and six D10 holes on a D76 circle.
- knob: turned knob, D40, with a spherical top, a rounded edge and a D6 shaft hole.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
import trimesh
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "examples"
MAX_FACES = 300_000
NOISE_SIGMA = 0.03
SEED = 20260926

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


def _edges(shape: TopoDS_Shape) -> list:
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    edges = []
    while explorer.More():
        edges.append(TopoDS.Edge(explorer.Current()))
        explorer.Next()
    return edges


def _fillet(shape: TopoDS_Shape, radius: float, select: Callable[[BRepAdaptor_Curve], bool]):
    maker = BRepFilletAPI_MakeFillet(shape)
    count = 0
    for edge in _edges(shape):
        if select(BRepAdaptor_Curve(edge)):
            maker.Add(radius, edge)
            count += 1
    if count == 0:
        raise RuntimeError(f"no edge selected for the R{radius} fillet")
    return maker.Shape()


def _line_at(curve: BRepAdaptor_Curve, direction: int, **fixed: float) -> bool:
    """A straight edge along axis `direction` (0 x, 1 y, 2 z) at the given coordinates."""
    if curve.GetType() != GeomAbs_Line:
        return False
    along = curve.Line().Direction().Coord(direction + 1)
    point = curve.Value(curve.FirstParameter())
    coordinates = {"x": point.X(), "y": point.Y(), "z": point.Z()}
    return abs(abs(along) - 1) < 1e-9 and all(
        abs(coordinates[axis] - value) < 1e-6 for axis, value in fixed.items()
    )


def _circle_at(curve: BRepAdaptor_Curve, radius: float, z: float) -> bool:
    if curve.GetType() != GeomAbs_Circle:
        return False
    circle = curve.Circle()
    return abs(circle.Radius() - radius) < 1e-6 and abs(circle.Location().Z() - z) < 1e-6


def _cylinder(x: float, y: float, z: float, radius: float, height: float, axis=(0, 0, 1)):
    frame = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(*axis))
    return BRepPrimAPI_MakeCylinder(frame, radius, height).Shape()


def bracket() -> TopoDS_Shape:
    base = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 80, 50, 8).Shape()
    upright = BRepPrimAPI_MakeBox(gp_Pnt(0, 42, 0), 80, 8, 60).Shape()
    shape = BRepAlgoAPI_Fuse(base, upright).Shape()
    shape = _fillet(shape, 6.0, lambda curve: _line_at(curve, 0, y=42, z=8))
    shape = _fillet(shape, 8.0, lambda curve: _line_at(curve, 2, y=0))
    for x in (20.0, 60.0):
        shape = BRepAlgoAPI_Cut(shape, _cylinder(x, 20, -1, 4.5, 10)).Shape()
    return BRepAlgoAPI_Cut(shape, _cylinder(40, 41, 38, 6.0, 10, axis=(0, 1, 0))).Shape()


def flange() -> TopoDS_Shape:
    shape = BRepAlgoAPI_Fuse(_cylinder(0, 0, 0, 50, 12), _cylinder(0, 0, 0, 25, 32)).Shape()
    shape = _fillet(shape, 3.0, lambda curve: _circle_at(curve, 25, 12))
    shape = BRepAlgoAPI_Cut(shape, _cylinder(0, 0, -1, 15, 34)).Shape()
    for index in range(6):
        angle = index * math.pi / 3
        hole = _cylinder(38 * math.cos(angle), 38 * math.sin(angle), -1, 5, 14)
        shape = BRepAlgoAPI_Cut(shape, hole).Shape()
    return shape


def knob() -> TopoDS_Shape:
    body = _cylinder(0, 0, 0, 20, 18)
    dome = BRepAlgoAPI_Common(
        BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, -8), 32).Shape(),
        _cylinder(0, 0, 18, 20, 20),
    ).Shape()
    shape = BRepAlgoAPI_Fuse(body, dome).Shape()
    shape = _fillet(shape, 4.0, lambda curve: _circle_at(curve, 20, 0))
    return BRepAlgoAPI_Cut(shape, _cylinder(0, 0, -1, 3, 13)).Shape()


def tessellate(shape: TopoDS_Shape) -> tuple[FloatArray, IntArray]:
    """Fine OCCT triangulation of every face, oriented outwards and welded."""
    BRepMesh_IncrementalMesh(shape, 0.005, False, 0.05, True)
    vertices, faces, offset = [], [], 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        transform = location.Transformation()
        nodes = [
            triangulation.Node(i).Transformed(transform)
            for i in range(1, triangulation.NbNodes() + 1)
        ]
        triangles = np.array(
            [triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]
        )
        if face.Orientation() == TopAbs_REVERSED:
            triangles = triangles[:, ::-1]
        vertices.append(np.array([(p.X(), p.Y(), p.Z()) for p in nodes]))
        faces.append(triangles - 1 + offset)
        offset += len(nodes)
        explorer.Next()
    mesh = trimesh.Trimesh(np.vstack(vertices), np.vstack(faces), process=False)
    mesh.merge_vertices(digits_vertex=6)
    return np.asarray(mesh.vertices), np.asarray(mesh.faces, dtype=np.int64)


def scan_like(shape: TopoDS_Shape, rng: np.random.Generator) -> trimesh.Trimesh:
    """Even triangles below MAX_FACES, noise along the normals and a tilted pose."""
    vertices, faces = tessellate(shape)
    edge = 0.6
    while True:
        fine_vertices, fine_faces = trimesh.remesh.subdivide_to_size(
            vertices, faces, max_edge=edge, max_iter=40
        )
        if len(fine_faces) <= MAX_FACES:
            break
        edge *= 1.15
    mesh = trimesh.Trimesh(fine_vertices, fine_faces, process=True)
    normals = np.asarray(mesh.vertex_normals)
    noisy = np.asarray(mesh.vertices) + normals * rng.normal(0.0, NOISE_SIGMA, (len(normals), 1))
    rotation = trimesh.transformations.euler_matrix(*np.radians(rng.uniform(-25, 25, 3)))
    rotation[:3, 3] = rng.uniform(-150, 150, 3)
    posed = trimesh.Trimesh(noisy, np.asarray(mesh.faces), process=False)
    posed.apply_transform(rotation)
    return posed


NOTICE = """Example scans of Mesh-to-CAD

bracket.stl, flange.stl and knob.stl are generated by scripts/generate-examples.py
from Open CASCADE models with simulated scanner noise (sigma 0.03 mm). They are
part of Mesh-to-CAD and may be used and redistributed under its MIT licence.
"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    for name, build in (("bracket", bracket), ("flange", flange), ("knob", knob)):
        mesh = scan_like(build(), rng)
        path = OUTPUT / f"{name}.stl"
        mesh.export(path, file_type="stl")
        size = np.ptp(mesh.vertices, axis=0)
        print(f"{path.name}: {len(mesh.faces):,} triangles, extent {np.round(size, 1)} mm")
    (OUTPUT / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")


if __name__ == "__main__":
    main()
