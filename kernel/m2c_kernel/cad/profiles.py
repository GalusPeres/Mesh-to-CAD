"""Sketch profiles as input of extrusions and revolutions.

A profile is a planar face plus a name per edge. Side faces of an extrusion
(and the faces a revolution sweeps) are tagged with these names, so they must
stay the same when an upstream parameter changes. The sketch provides the
entity id of every profile edge (`SketchResult.edge_names`); without it the
edges are named by loop and position, which is stable as long as the sketch
itself does not change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Curve,
    TopAbs_EDGE,
    TopAbs_VERTEX,
    TopExp_Explorer,
    TopoDS,
    TopoDS_Shape,
)
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import SketchResult
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError


@dataclass(frozen=True)
class Profile:
    """A planar profile face and the names of its edges (in `profile_edges` order)."""

    face: Any
    edge_names: tuple[str, ...]


def profile_edges(face: TopoDS_Shape) -> list[TopoDS_Shape]:
    """Edges of a face in explorer order (stable for equal input)."""
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    edges: list[TopoDS_Shape] = []
    while explorer.More():
        edges.append(explorer.Current())
        explorer.Next()
    return edges


def sketch_profiles(sketch: SketchResult, loops: Sequence[str] | None) -> list[Profile]:
    """The profiles of the loops with these ids (all closed loops for None), with edge names."""
    if not sketch.profile_faces:
        raise KernelError(ErrorCode.PROFILE_OPEN)
    wanted = None if loops is None else list(loops)
    if wanted is not None:
        missing = [loop for loop in wanted if loop not in sketch.loop_ids]
        if missing:
            raise KernelError(ErrorCode.LOOP_NOT_FOUND, {"loop": missing[0]})
        if not wanted:
            raise KernelError(ErrorCode.PROFILE_OPEN)
    names_by_face: tuple[tuple[str, ...], ...] = getattr(sketch, "edge_names", ())
    profiles = []
    for index, face in enumerate(sketch.profile_faces):
        loop_id = sketch.loop_ids[index] if index < len(sketch.loop_ids) else f"l{index}"
        if wanted is not None and loop_id not in wanted:
            continue
        edge_count = len(profile_edges(face))
        names = names_by_face[index] if index < len(names_by_face) else ()
        if len(names) != edge_count:
            names = tuple(f"{loop_id}.{position}" for position in range(edge_count))
        profiles.append(Profile(face, tuple(names)))
    return profiles


def sketch_line(sketch: SketchResult, entity: str) -> tuple[FloatArray, FloatArray]:
    """Point and unit direction of the sketch line `entity` (part coordinates).

    Uses the sketch's line table when it has one, otherwise a profile edge with
    that entity name.
    """
    lines = getattr(sketch, "lines", {})
    if entity in lines:
        start, end = (np.asarray(point, dtype=np.float64) for point in lines[entity])
        if np.linalg.norm(end - start) > 1e-9:
            return start, unit(end - start)
    for profile in sketch_profiles(sketch, None):
        for edge, name in zip(profile_edges(profile.face), profile.edge_names, strict=True):
            if name != entity:
                continue
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
            start = np.asarray(curve.Value(curve.FirstParameter()).Coord())
            end = np.asarray(curve.Value(curve.LastParameter()).Coord())
            middle = np.asarray(
                curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2).Coord()
            )
            chord = end - start
            straight = np.linalg.norm(np.cross(middle - start, unit(chord))) < 1e-7
            if np.linalg.norm(chord) > 1e-9 and straight:
                return start, unit(chord)
    raise KernelError(ErrorCode.AXIS_NOT_FOUND, {"entity": entity})


def shape_vertices(shape: TopoDS_Shape) -> FloatArray:
    """Positions of all vertices of a shape, (n, 3)."""
    explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
    points = []
    while explorer.More():
        points.append(BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current())).Coord())
        explorer.Next()
    return np.array(points, dtype=np.float64).reshape(-1, 3)


def edge_samples(edge: TopoDS_Shape, count: int = 17) -> FloatArray:
    """`count` points along an edge, including both ends."""
    curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
    parameters = np.linspace(curve.FirstParameter(), curve.LastParameter(), count)
    return np.array([curve.Value(float(t)).Coord() for t in parameters], dtype=np.float64)


def profile_samples(profiles: Sequence[Profile]) -> FloatArray:
    """Points along every edge of the profiles (curved edges included)."""
    return np.vstack(
        [edge_samples(edge) for profile in profiles for edge in profile_edges(profile.face)]
    )
