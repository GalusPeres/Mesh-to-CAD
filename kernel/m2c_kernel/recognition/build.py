"""Editable CAD features from recognised features: plane, sketch and extrusions.

For every base plane with chosen features the document gets

- a `fit` plane through the plane's triangles with its normal and a point fixed, so
  its orientation is known here and the sketches face out of the material;
- one `sketch` per level (the base plane, or a pocket floor) and height on that
  plane, holding the outlines' chains as lines, arcs and circles with their tangency,
  parallel and equality constraints, free profiles included;
- one `extrude` per family (equal shape, size and height), named like the family
  when the client gives names: bosses are added, pockets cut (through holes a
  little beyond the part), so the user edits one value per family; without a body
  every boss becomes a body of its own (a body is one solid);
- for a feature with an inclined top, a plane fitted to its top and an extrusion up
  to that plane of its own (`build_inclined.py`).

The sketches compare themselves with the scan where the outlines were measured, at
half the height (depth) of their features, not at the foot, which fillets widen.
Added and cut extrusions also reach `OVERLAP_MM` back across their sketch plane: the
fitted plane lies within the scan noise of the body's face, and a boss that only
touches the body (or a pocket that leaves a skin) would not combine.

Order: bosses on the plane, then pockets, then the bosses standing in pockets (a
pocket would otherwise cut them away).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature, Recognition
from m2c_kernel.recognition.build_inclined import inclined_extrusion
from m2c_kernel.recognition.build_rounding import TopEdges, top_edges
from m2c_kernel.recognition.planes import BasePlane
from m2c_kernel.recognition.sketch_ops import SketchDraft, as_list, chain_entities

THROUGH_MARGIN_MM = 1.0
"""Through holes are cut this much beyond the far side."""
OVERLAP_MM = 0.5
"""Added and cut extrusions start this far behind their sketch plane."""
PLANE_TOLERANCE_FACTOR = 4.0


# Operations ------------------------------------------------------------------------------


@dataclass(frozen=True)
class NewFeatureOp:
    """One feature to add: its type, JSON parameters and the arrays they reference."""

    type: str
    params: dict[str, Any]
    buffers: tuple[np.ndarray, ...] = ()
    name: str | None = None


@dataclass(frozen=True)
class FeaturePlan:
    """Features to add, in order, and the chosen features left out.

    References use the ids the document will assign (`f<next_id>`, ...).
    """

    features: list[NewFeatureOp]
    skipped: list[int]
    top_edges: list[TopEdges] = field(default_factory=list)
    """Where the built features' top edges are, for their fillets."""


def plan_features(
    recognition: Recognition,
    chosen: Sequence[int],
    plane_faces: Sequence[np.ndarray],
    next_id: int,
    target_body: str | None,
    names: Mapping[int, str] | None = None,
    top_faces: Callable[[int], np.ndarray] = lambda _: np.zeros(0, dtype=np.uint32),
) -> FeaturePlan:
    """Plane, sketches and extrusions for the chosen features.

    Args:
        recognition: The recognised planes and features.
        chosen: Indices of the features to build.
        plane_faces: Per recognised plane, its triangles in the full scan.
        next_id: The document's next feature number.
        target_body: Body the bosses join and the pockets cut; None makes the bosses
            new bodies and leaves pockets out.
        names: Display names by feature index; a family's extrusions take the name
            of its first feature.
        top_faces: The full scan's triangles of a feature's inclined top, by index.
    """
    planned: list[NewFeatureOp] = []
    skipped: list[int] = []
    edges: list[TopEdges] = []
    number = next_id

    def add(
        kind: str,
        params: dict[str, Any],
        buffers: tuple[np.ndarray, ...] = (),
        name: str | None = None,
    ) -> str:
        nonlocal number
        feature_id = f"f{number}"
        number += 1
        planned.append(NewFeatureOp(kind, params, buffers, name))
        return feature_id

    features = recognition.features
    by_plane: dict[int, list[int]] = {}
    for index in chosen:
        feature = features[index]
        if feature.relief.kind == "pocket" and target_body is None:
            skipped.append(index)
            continue
        by_plane.setdefault(feature.plane, []).append(index)

    for plane_index, members in by_plane.items():
        plane = recognition.planes[plane_index]
        faces = np.asarray(plane_faces[plane_index], dtype=np.uint32)
        plane_id = add(
            "fit",
            {
                "faces": {"$buf": 0, "dtype": "uint32", "shape": [len(faces)]},
                "kind": "plane",
                "fixed": {"direction": as_list(plane.normal), "point": as_list(plane.origin)},
                "snap": False,
            },
            (faces,),
        )
        shift = np.array([plane.origin @ plane.x_axis, plane.origin @ plane.y_axis])
        for stage in _stages(features, members):
            inclined = [i for i in stage if features[i].relief.top == "inclined"]
            flat = [i for i in stage if i not in inclined]
            if flat:
                edges += _extrusions(
                    add, plane, plane_id, shift, features, flat, target_body, names or {}
                )
            edges += [
                inclined_extrusion(
                    add,
                    plane,
                    plane_id,
                    shift,
                    index,
                    features[index],
                    top_faces(index),
                    target_body,
                    (names or {}).get(index),
                    OVERLAP_MM,
                )
                for index in inclined
            ]
    return FeaturePlan(planned, skipped, edges)


def _stages(features: Sequence[Feature], members: list[int]) -> list[list[int]]:
    """Bosses on the plane, pockets, then bosses standing in pockets."""
    on_plane = [
        i
        for i in members
        if features[i].relief.kind == "boss" and features[i].relief.parent is None
    ]
    pockets = [i for i in members if features[i].relief.kind == "pocket"]
    nested = [
        i
        for i in members
        if features[i].relief.kind == "boss" and features[i].relief.parent is not None
    ]
    return [stage for stage in (on_plane, pockets, nested) if stage]


def _extrusions(
    add: Any,
    plane: BasePlane,
    plane_id: str,
    shift: FloatArray,
    features: Sequence[Feature],
    stage: list[int],
    target_body: str | None,
    names: Mapping[int, str],
) -> list[TopEdges]:
    """Sketches and extrusions of one stage; returns where their top edges are."""
    edges: list[TopEdges] = []
    by_height: dict[tuple[float, float], list[int]] = {}
    for index in stage:
        relief = features[index].relief
        by_height.setdefault((round(relief.level, 4), round(relief.height, 4)), []).append(index)
    for (level, height), indices in by_height.items():
        sketch = SketchDraft()
        entities = {
            index: chain_entities(sketch, features[index].outline.chain, shift) for index in indices
        }
        loops = {index: ids[0] for index, ids in entities.items()}
        # Bosses rise along the normal, pockets sink against it: compare with the
        # scan halfway up, where the outlines were measured.
        sign = 1.0 if features[indices[0]].relief.kind == "boss" else -1.0
        sketch_id = add(
            "sketch",
            {
                "section": {
                    "type": "planar",
                    "plane": {"type": "feature", "feature": plane_id},
                    "offset": level,
                    "sectionOffset": sign * height / 2.0,
                    "xDirection": as_list(plane.x_axis),
                },
                "points": sketch.points,
                "entities": sketch.entities,
                "constraints": sketch.constraints,
            },
        )
        families: dict[tuple[object, ...], list[int]] = {}
        for index in loops:
            families.setdefault(_family(index, features[index]), []).append(index)
        for members in families.values():
            relief = features[members[0]].relief
            depth = relief.height + THROUGH_MARGIN_MM if relief.top == "through" else relief.height
            direction = "normal" if relief.kind == "boss" else "reversed"
            name = names.get(members[0])
            if not target_body:
                # A new body is one solid: every boss of the family becomes its own.
                for index in members:
                    body = add(
                        "extrude",
                        {
                            "sketch": sketch_id,
                            "loops": [loops[index]],
                            "direction": direction,
                            "extent": {"type": "distance", "forward": depth},
                            "operation": "newBody",
                        },
                        name=name,
                    )
                    edges.append(
                        top_edges(index, features[index], plane, entities[index], body, body)
                    )
                continue
            extrusion = add(
                "extrude",
                {
                    "sketch": sketch_id,
                    "loops": [loops[index] for index in members],
                    "direction": direction,
                    "extent": {"type": "distance", "forward": depth, "backward": OVERLAP_MM},
                    "operation": "add" if relief.kind == "boss" else "cut",
                    "targetBody": target_body,
                },
                name=name,
            )
            edges += [
                top_edges(index, features[index], plane, entities[index], target_body, extrusion)
                for index in members
            ]
    return edges


def _family(index: int, feature: Feature) -> tuple[object, ...]:
    """Features made alike: same kind, top, height, shape and size (free profiles differ)."""
    relief, outline = feature.relief, feature.outline
    if outline.kind == "profile":
        return ("profile", index)
    size = tuple(
        round(value, 3)
        for name, value in outline.named().items()
        if name not in ("cx", "cy", "angle", "start")
    )
    return (relief.kind, relief.top, round(relief.height, 4), outline.kind, size)


def plane_faces(
    plane: BasePlane,
    centroids: FloatArray,
    face_normals: FloatArray,
    noise: float,
) -> np.ndarray:
    """The plane's triangles in another copy of the scan (the full one)."""
    tolerance = max(PLANE_TOLERANCE_FACTOR * noise, 0.05)
    distance = np.abs((centroids - plane.origin) @ plane.normal)
    agree = face_normals @ plane.normal > np.cos(np.radians(15.0))
    result: np.ndarray = np.flatnonzero((distance < tolerance) & agree).astype(np.uint32)
    return result
