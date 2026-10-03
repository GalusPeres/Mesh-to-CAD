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
  every boss becomes a body of its own (a body is one solid).

The sketches compare themselves with the scan where the outlines were measured, at
half the height (depth) of their features, not at the foot, which fillets widen.
Added and cut extrusions also reach `OVERLAP_MM` back across their sketch plane: the
fitted plane lies within the scan noise of the body's face, and a boss that only
touches the body (or a pocket that leaves a skin) would not combine.

Order: bosses on the plane, then pockets, then the bosses standing in pockets (a
pocket would otherwise cut them away).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature, Recognition
from m2c_kernel.recognition.chain import Chain
from m2c_kernel.recognition.planes import BasePlane

THROUGH_MARGIN_MM = 1.0
"""Through holes are cut this much beyond the far side."""
OVERLAP_MM = 0.5
"""Added and cut extrusions start this far behind their sketch plane."""
PLANE_TOLERANCE_FACTOR = 4.0


@dataclass
class _Sketch:
    """Points, entities and constraints of one sketch under construction (JSON form)."""

    points: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    counter: int = 0

    def point(self, xy: FloatArray) -> str:
        self.counter += 1
        pid = f"p{self.counter}"
        self.points.append({"id": pid, "x": float(xy[0]), "y": float(xy[1])})
        return pid

    def entity(self, kind: str, **values: Any) -> str:
        self.counter += 1
        eid = f"e{self.counter}"
        self.entities.append({"type": kind, "id": eid, **values})
        return eid

    def line(self, start: str, end: str) -> str:
        return self.entity("line", start=start, end=end)

    def arc(self, start: str, end: str, centre: FloatArray, radius: float, ccw: bool) -> str:
        return self.entity(
            "arc",
            start=start,
            end=end,
            center=[float(centre[0]), float(centre[1])],
            radius=float(radius),
            ccw=ccw,
        )

    def constrain(self, kind: str, *refs: str) -> None:
        self.constraints.append({"kind": kind, "refs": list(refs)})


def chain_loop(sketch: _Sketch, chain: Chain, shift: FloatArray) -> str:
    """Add an outline's lines and arcs to the sketch (moved by `shift`); returns its loop id.

    Neighbouring edges share their point; the chain's relations become constraints.
    """
    if chain.is_circle:
        edge = chain.edges[0]
        assert edge.centre is not None
        centre = np.array(edge.centre) + shift
        return sketch.entity("circle", center=_list(centre), radius=edge.radius)
    ids = [sketch.point(np.array(edge.start) + shift) for edge in chain.edges]
    entities: list[str] = []
    for i, edge in enumerate(chain.edges):
        start, end = ids[i], ids[(i + 1) % len(ids)]
        if edge.centre is None:
            entities.append(sketch.line(start, end))
        else:
            centre = np.array(edge.centre) + shift
            entities.append(sketch.arc(start, end, centre, edge.radius, edge.ccw))
    for kind, refs in chain.relations:
        sketch.constrain(kind, *(entities[ref] for ref in refs))
    return entities[0]


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


def plan_features(
    recognition: Recognition,
    chosen: Sequence[int],
    plane_faces: Sequence[np.ndarray],
    next_id: int,
    target_body: str | None,
    names: Mapping[int, str] | None = None,
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
    """
    planned: list[NewFeatureOp] = []
    skipped: list[int] = []
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
                "fixed": {"direction": _list(plane.normal), "point": _list(plane.origin)},
                "snap": False,
            },
            (faces,),
        )
        shift = np.array([plane.origin @ plane.x_axis, plane.origin @ plane.y_axis])
        for stage in _stages(features, members):
            _extrusions(add, plane, plane_id, shift, features, stage, target_body, names or {})
    return FeaturePlan(planned, skipped)


def _list(values: np.ndarray) -> list[float]:
    return [float(value) for value in values]


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
) -> None:
    by_height: dict[tuple[float, float], list[int]] = {}
    for index in stage:
        relief = features[index].relief
        by_height.setdefault((round(relief.level, 4), round(relief.height, 4)), []).append(index)
    for (level, height), indices in by_height.items():
        sketch = _Sketch()
        loops = {
            index: chain_loop(sketch, features[index].outline.chain, shift) for index in indices
        }
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
                    "xDirection": _list(plane.x_axis),
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
                    add(
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
                continue
            add(
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
