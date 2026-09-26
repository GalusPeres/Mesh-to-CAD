"""Test parts built with Open CASCADE, tessellated like a scan, with exact ground truth.

- `block_part`: 100 x 70 x 20 block with R6 vertical edge fillets, a D30 boss with an R3
  torus fillet and a 2 mm chamfer cone, a D16 through hole and an R9 spherical dimple
  (16 B-Rep faces: planes, cylinders, a cone, a torus, a sphere).
- `plate_part`: 100 x 60 x 10 plate with three R8 corner fillets, an 8 mm chamfer, an R10
  notch and two D12 holes (for section sketches).

Every triangle keeps the index of the B-Rep face it came from (`labels`), and every face
carries its analytic surface, so segmentation, fitting, sketches and deviation can be scored.
Add noise with `add_scanner_noise` and a pose with `random_pose`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

import numpy as np
import numpy.typing as npt
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.GeomAbs import (
    GeomAbs_Circle,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Line,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from scipy.spatial import cKDTree

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepMesh_IncrementalMesh,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopExp_Explorer,
    TopLoc_Location,
    TopoDS,
    TopoDS_Shape,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
)
from m2c_kernel.fitting.api import signed_distance
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import vec3

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class SyntheticPart:
    """A clean scan-like mesh of an OCCT solid with per-triangle ground truth."""

    shape: TopoDS_Shape
    vertices: FloatArray
    faces: IntArray
    labels: IntArray
    """B-Rep face index per triangle, in `TopExp_Explorer` order."""
    surfaces: tuple[Primitive | None, ...]
    """Analytic surface per B-Rep face; None for other surface types."""

    def distance_to_truth(self, points: FloatArray, k: int = 8) -> FloatArray:
        """Signed distance of points to the true part surface (positive outside)."""
        centroids = self.vertices[self.faces].mean(axis=1)
        _, nearest = cKDTree(centroids).query(points, k=k, workers=-1)
        candidates = self.labels[nearest]
        best = np.full(len(points), np.inf)
        for face_id, surface in enumerate(self.surfaces):
            rows = np.nonzero((candidates == face_id).any(axis=1))[0]
            if surface is None or len(rows) == 0:
                continue
            distance = signed_distance(surface, points[rows])
            better = np.abs(distance) < np.abs(best[rows])
            best[rows[better]] = distance[better]
        return best


def _explore(shape: TopoDS_Shape, kind: Any) -> list[Any]:
    explorer = TopExp_Explorer(shape, kind)
    items = []
    while explorer.More():
        items.append(explorer.Current())
        explorer.Next()
    return items


def _xyz(point: Any) -> tuple[float, float, float]:
    return (float(point.X()), float(point.Y()), float(point.Z()))


def _surface(face: Any) -> Primitive | None:
    adaptor = BRepAdaptor_Surface(face)
    kind = adaptor.GetType()
    if kind == GeomAbs_Plane:
        plane = adaptor.Plane()
        normal = np.array(_xyz(plane.Axis().Direction()))
        if face.Orientation() == TopAbs_REVERSED:
            normal = -normal
        return Plane(origin=_xyz(plane.Location()), normal=vec3(normal))
    if kind == GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        return Cylinder(
            origin=_xyz(cylinder.Location()),
            axis=_xyz(cylinder.Axis().Direction()),
            radius=float(cylinder.Radius()),
        )
    if kind == GeomAbs_Cone:
        cone = adaptor.Cone()
        axis = np.array(_xyz(cone.Axis().Direction()))
        if cone.SemiAngle() < 0:  # our convention: the axis points from the apex into the opening
            axis = -axis
        return Cone(apex=_xyz(cone.Apex()), axis=vec3(axis), half_angle=abs(cone.SemiAngle()))
    if kind == GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        return Sphere(center=_xyz(sphere.Location()), radius=float(sphere.Radius()))
    if kind == GeomAbs_Torus:
        torus = adaptor.Torus()
        return Torus(
            center=_xyz(torus.Location()),
            axis=_xyz(torus.Axis().Direction()),
            major_radius=float(torus.MajorRadius()),
            minor_radius=float(torus.MinorRadius()),
        )
    return None


def tessellate_part(shape: TopoDS_Shape, max_edge: float) -> SyntheticPart:
    """Fine tessellation, welded and subdivided to `max_edge`, with face labels."""
    BRepMesh_IncrementalMesh(shape, 0.004, False, 0.05, True)
    vertices, faces, labels, surfaces = [], [], [], []
    offset = 0
    for face_id, item in enumerate(_explore(shape, TopAbs_FACE)):
        face = TopoDS.Face(item)
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        transform = location.Transformation()
        nodes = np.array(
            [
                _xyz(triangulation.Node(i).Transformed(transform))
                for i in range(1, triangulation.NbNodes() + 1)
            ]
        )
        triangles = (
            np.array(
                [triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]
            )
            - 1
        )
        if face.Orientation() == TopAbs_REVERSED:
            triangles = triangles[:, ::-1]
        vertices.append(nodes)
        faces.append(triangles + offset)
        labels.append(np.full(len(triangles), face_id))
        surfaces.append(_surface(face))
        offset += len(nodes)
    mesh = trimesh.Trimesh(np.vstack(vertices), np.vstack(faces), process=False)
    mesh.merge_vertices(digits_vertex=6)
    fine_vertices, fine_faces, index = trimesh.remesh.subdivide_to_size(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        max_edge=max_edge,
        max_iter=30,
        return_index=True,
    )
    return SyntheticPart(
        shape=shape,
        vertices=np.asarray(fine_vertices, dtype=np.float64),
        faces=np.asarray(fine_faces, dtype=np.int64),
        labels=np.concatenate(labels)[index].astype(np.int64),
        surfaces=tuple(surfaces),
    )


def build_test_block() -> TopoDS_Shape:
    shape = BRepPrimAPI_MakeBox(100.0, 70.0, 20.0).Shape()
    fillet = BRepFilletAPI_MakeFillet(shape)
    for item in _explore(shape, TopAbs_EDGE):
        curve = BRepAdaptor_Curve(TopoDS.Edge(item))
        if curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.99:
            fillet.Add(6.0, TopoDS.Edge(item))
    shape = fillet.Shape()

    boss = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(70, 35, 20), gp_Dir(0, 0, 1)), 15.0, 15.0)
    shape = BRepAlgoAPI_Fuse(shape, boss.Shape()).Shape()
    shape = _round_circle(shape, radius=15.0, z=20.0, size=3.0, chamfer=False)
    shape = _round_circle(shape, radius=15.0, z=35.0, size=2.0, chamfer=True)

    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(25, 35, -1), gp_Dir(0, 0, 1)), 8.0, 22.0)
    shape = BRepAlgoAPI_Cut(shape, hole.Shape()).Shape()
    dimple = BRepPrimAPI_MakeSphere(gp_Pnt(40, 12, 26.0), 9.0)
    return BRepAlgoAPI_Cut(shape, dimple.Shape()).Shape()


def _round_circle(
    shape: TopoDS_Shape, *, radius: float, z: float, size: float, chamfer: bool
) -> TopoDS_Shape:
    maker = BRepFilletAPI_MakeChamfer(shape) if chamfer else BRepFilletAPI_MakeFillet(shape)
    for item in _explore(shape, TopAbs_EDGE):
        curve = BRepAdaptor_Curve(TopoDS.Edge(item))
        if curve.GetType() != GeomAbs_Circle:
            continue
        circle = curve.Circle()
        if abs(circle.Radius() - radius) < 1e-6 and abs(circle.Location().Z() - z) < 1e-6:
            maker.Add(size, TopoDS.Edge(item))
    return maker.Shape()


def build_test_plate() -> TopoDS_Shape:
    shape = BRepPrimAPI_MakeBox(gp_Pnt(-50, -30, 0), 100, 60, 10).Shape()
    chamfer = BRepFilletAPI_MakeChamfer(shape)
    chamfer.Add(8.0, _vertical_edge_at(shape, -50, -30))
    shape = chamfer.Shape()
    fillet = BRepFilletAPI_MakeFillet(shape)
    for x, y in ((50, -30), (50, 30), (-50, 30)):
        fillet.Add(8.0, _vertical_edge_at(shape, x, y))
    shape = fillet.Shape()
    up = gp_Dir(0, 0, 1)
    for cx, cy, r in ((0, 30, 10), (-25, -5, 6), (25, -5, 6)):
        tool = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(cx, cy, -1), up), r, 12).Shape()
        shape = BRepAlgoAPI_Cut(shape, tool).Shape()
    return shape


def _vertical_edge_at(shape: TopoDS_Shape, x: float, y: float) -> Any:
    for item in _explore(shape, TopAbs_EDGE):
        edge = TopoDS.Edge(item)
        curve = BRepAdaptor_Curve(edge)
        start = curve.Value(curve.FirstParameter())
        end = curve.Value(curve.LastParameter())
        if all(abs(p.X() - x) < 1e-6 and abs(p.Y() - y) < 1e-6 for p in (start, end)):
            return edge
    raise LookupError((x, y))


@cache
def block_part(max_edge: float = 1.0) -> SyntheticPart:
    """The 16-face test block; cached per process because tessellation takes seconds."""
    return tessellate_part(build_test_block(), max_edge)


@cache
def plate_part(max_edge: float = 1.0) -> SyntheticPart:
    """The test plate for section sketches."""
    return tessellate_part(build_test_plate(), max_edge)
