"""Planar profile faces of a sketch (algorithms-cad.md 1.9).

Consecutive entities share one point object, so every wire closes without any
tolerance handling (no `ShapeFix_Wire`, which would inflate vertex tolerances).
Outer loops run counter-clockwise, holes clockwise; loops at odd nesting depth
become holes of their parent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# Arcs need gp_Circ and GC_MakeArcOfCircle, which cad/occ_compat.py does not export yet
# (interface request T5); both names are unchanged between OCCT 7 and 8.
from OCP.GC import GC_MakeArcOfCircle
from OCP.gp import gp_Circ

from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Curve,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepCheck_Analyzer,
    TopAbs_EDGE,
    TopExp_Explorer,
    TopoDS,
    gp_Ax2,
    gp_Ax3,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
)
from m2c_kernel.document.results import PlaneFrame
from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    FloatArray,
    Line,
    WorkSketch,
    arc_midpoint,
    entity_distances,
)
from m2c_kernel.sketch.profile import Loop, nesting
from m2c_kernel.sketch.section import to_uv, to_xyz


class ProfileError(ValueError):
    """A closed loop that does not give a valid planar face."""

    def __init__(self, loop: str) -> None:
        super().__init__(loop)
        self.loop = loop


@dataclass(frozen=True)
class ProfileFace:
    loop_id: str
    face: Any
    edge_names: tuple[str, ...]
    """Entity id per face edge, in `TopExp_Explorer` order."""


def _pnt(frame: PlaneFrame, uv: FloatArray) -> gp_Pnt:
    x, y, z = to_xyz(frame, uv)[0]
    return gp_Pnt(float(x), float(y), float(z))


def _edges(
    sketch: WorkSketch, loop: Loop, frame: PlaneFrame, points: dict[str, gp_Pnt]
) -> list[tuple[str, Any]]:
    edges = []
    for eid in loop.entities:
        entity = sketch.entities[eid]
        if isinstance(entity, Circle):
            axis = gp_Ax2(_pnt(frame, entity.center), gp_Dir(*frame.normal), gp_Dir(*frame.x_dir))
            edges.append((eid, BRepBuilderAPI_MakeEdge(gp_Circ(axis, entity.radius)).Edge()))
            continue
        start, end = points[entity.start], points[entity.end]
        if isinstance(entity, Line):
            edges.append((eid, BRepBuilderAPI_MakeEdge(start, end).Edge()))
        else:
            assert isinstance(entity, Arc)
            middle = arc_midpoint(
                entity.center,
                entity.radius,
                sketch.xy(entity.start),
                sketch.xy(entity.end),
                entity.ccw,
            )
            curve = GC_MakeArcOfCircle(start, _pnt(frame, middle), end).Value()
            edges.append((eid, BRepBuilderAPI_MakeEdge(curve).Edge()))
    return edges


def _wire(edges: list[tuple[str, Any]], reverse: bool) -> Any:
    builder = BRepBuilderAPI_MakeWire()
    for _, edge in edges:
        builder.Add(edge)
    if not builder.IsDone():
        raise ValueError("wire")
    wire = builder.Wire()
    return TopoDS.Wire(wire.Reversed()) if reverse else wire


def _edge_names(
    sketch: WorkSketch, face: Any, frame: PlaneFrame, entity_ids: list[str]
) -> tuple[str, ...]:
    """The entity of each face edge, found by the distance of the edge's midpoint.

    The wire builder may copy edges, so identity comparisons are not reliable.
    """
    names = []
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    while explorer.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge(explorer.Current()))
        middle = curve.Value(0.5 * (curve.FirstParameter() + curve.LastParameter()))
        uv = to_uv(frame, np.array(middle.Coord())[None, :])
        distances = [
            float(entity_distances(sketch, sketch.entities[eid], uv)[0]) for eid in entity_ids
        ]
        names.append(entity_ids[int(np.argmin(distances))])
        explorer.Next()
    return tuple(names)


def profile_faces(sketch: WorkSketch, loops: list[Loop], frame: PlaneFrame) -> list[ProfileFace]:
    """One face per outer loop, with its direct holes."""
    points = {pid: _pnt(frame, p.xy[None, :]) for pid, p in sketch.points.items()}
    plane = gp_Pln(gp_Ax3(gp_Pnt(*frame.origin), gp_Dir(*frame.normal), gp_Dir(*frame.x_dir)))
    faces = []
    for outer, holes in nesting(loops):
        loop = loops[outer]
        try:
            outer_edges = _edges(sketch, loop, frame, points)
            builder = BRepBuilderAPI_MakeFace(plane, _wire(outer_edges, loop.area < 0), True)
            entity_ids = list(loop.entities)
            for index in holes:
                hole_edges = _edges(sketch, loops[index], frame, points)
                builder.Add(_wire(hole_edges, loops[index].area > 0))
                entity_ids += loops[index].entities
            face = builder.Face()
        except Exception as failure:  # OCCT reports construction problems as Standard_Failure
            raise ProfileError(loop.id) from failure
        if not BRepCheck_Analyzer(face).IsValid():
            raise ProfileError(loop.id)
        faces.append(ProfileFace(loop.id, face, _edge_names(sketch, face, frame, entity_ids)))
    return faces


def line_ends(sketch: WorkSketch, frame: PlaneFrame) -> dict[str, tuple[FloatArray, FloatArray]]:
    """Start and end of every line in part coordinates (revolve axes)."""
    result = {}
    for entity in sketch.entities.values():
        if isinstance(entity, Line):
            ends = to_xyz(frame, np.vstack([sketch.xy(entity.start), sketch.xy(entity.end)]))
            result[entity.id] = (ends[0], ends[1])
    return result
