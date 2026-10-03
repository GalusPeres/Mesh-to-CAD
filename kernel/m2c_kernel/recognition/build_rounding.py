"""Fillets on the top edges of built features, one per group with the group's radius.

While planning, every extrusion notes where its features' top edges are: per sketch
entity of the outline, a point on the edge at the top (`TopEdges`). Once the
extrusions are evaluated, each point finds its edge on the body: the one nearest the
point between the extrusion's side face of that entity and any other face (a boss's
top, or the face a pocket is sunk into). The fillet references the edge by both face
tags and the point, like the fillet tool does (ARCHITECTURE.md 4.5).

Equal features share one fillet and its radius (design intent); bosses built as bodies
of their own get one fillet each, since a fillet rounds the edges of one body.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from m2c_kernel.cad.occ_compat import EdgeFaceMap, TopAbs_EDGE, TopAbs_FACE, TopExp, TopoDS
from m2c_kernel.cad.tags import faces_of, point_distance
from m2c_kernel.document.results import Body
from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature
from m2c_kernel.recognition.chain import Chain, edge_points
from m2c_kernel.recognition.planes import BasePlane

MAX_EDGE_DISTANCE_MM = 0.05
"""A top-edge point lies on its edge; farther means the edge is gone (cut away)."""


@dataclass(frozen=True)
class TopEdges:
    """Where a built feature's top edges are (part coordinates)."""

    feature: int
    """Index of the feature in the recognition."""
    body: str
    """The body the edges belong to."""
    extrusion: str
    """The extrusion whose side faces are the feature's walls."""
    edges: tuple[tuple[str, FloatArray], ...]
    """Per outline entity: its id and a point in the middle of its top edge."""


def top_edges(
    index: int,
    feature: Feature,
    plane: BasePlane,
    entities: Sequence[str],
    body: str,
    extrusion: str,
) -> TopEdges:
    """The top edges of one feature, from its outline entities (in chain order)."""
    relief = feature.relief
    middles = _edge_middles(feature.outline.chain)
    heights = (
        relief.top_at(middles) if relief.kind == "boss" else np.full(len(middles), relief.level)
    )
    points = plane.from_plane(np.column_stack([middles, heights]))
    return TopEdges(index, body, extrusion, tuple(zip(entities, points, strict=True)))


@dataclass(frozen=True)
class PlannedFillet:
    params: dict[str, Any]
    """The fillet's parameters (JSON form)."""
    features: list[int]
    """The features whose top edges it rounds."""


def fillet_ops(
    edges: Sequence[TopEdges],
    radii: Mapping[int, float],
    groups: Sequence[int],
    bodies: Mapping[str, Body],
) -> tuple[list[PlannedFillet], list[int]]:
    """One fillet per group and body, and the features whose top edges were not found.

    Args:
        edges: The top edges of the built features.
        radii: The radius to round each feature's edges with, by feature index.
        groups: The group of every feature of the recognition.
        bodies: The evaluated bodies after the extrusions.
    """
    fillets: dict[tuple[int, str], PlannedFillet] = {}
    missing: list[int] = []
    for item in edges:
        radius = radii.get(item.feature)
        if not radius:
            continue
        body = bodies.get(item.body)
        refs = [
            ref
            for entity, point in item.edges
            if body is not None
            and (ref := edge_ref(body, f"{item.extrusion}:side:{entity}", point)) is not None
        ]
        if not refs:
            missing.append(item.feature)
            continue
        params = {"targetBody": item.body, "edges": [], "mode": "fillet", "size": radius}
        fillet = fillets.setdefault((groups[item.feature], item.body), PlannedFillet(params, []))
        fillet.params["edges"].extend(refs)
        fillet.features.append(item.feature)
    return list(fillets.values()), missing


def edge_ref(body: Body, side: str, point: FloatArray) -> dict[str, Any] | None:
    """The reference of the edge of face `side` nearest `point`, or None if none is there."""
    face_map = faces_of(body.shape)
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(body.shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    location = (float(point[0]), float(point[1]), float(point[2]))
    best: tuple[float, list[str]] | None = None
    for index in range(1, edge_faces.Extent() + 1):
        faces = edge_faces.FindFromIndex(index)
        tags = sorted(
            {
                body.face_tags[i - 1]
                for face in faces
                if 0 < (i := face_map.FindIndex(face)) <= len(body.face_tags)
            }
        )
        if side not in tags or len(tags) != 2:
            continue
        distance = point_distance(location, TopoDS.Edge(edge_faces.FindKey(index)))
        if best is None or distance < best[0]:
            best = (distance, tags)
    if best is None or best[0] > MAX_EDGE_DISTANCE_MM:
        return None
    return {"faces": best[1], "point": list(location)}


def _edge_middles(chain: Chain) -> FloatArray:
    """A point in the middle of every edge of the chain (plane frame)."""
    middles = []
    for edge in chain.edges:
        points = edge_points(edge)
        if edge.centre is None:
            middles.append(points.mean(axis=0))
        else:
            middles.append(points[len(points) // 2])
    return np.array(middles, dtype=np.float64).reshape(-1, 2)
