"""Editable CAD features from recognised features: plane, sketch and extrusions.

For every base plane with chosen features the document gets

- a `fit` plane through the plane's triangles with its normal and a point fixed, so
  its orientation is known here and the sketches face out of the material;
- one `sketch` per level on that plane (the base plane, or a pocket floor) holding
  the outlines as lines, arcs and circles with tangency and equality constraints;
- one `extrude` per family (equal shape, size and height), named like the family
  when the client gives names: bosses are added, pockets cut (through holes a
  little beyond the part), so the user edits one value per family; without a body
  every boss becomes a body of its own (a body is one solid).

The sketches compare themselves with the scan where the outlines were measured, at
half the height (depth) of their features, not at the foot, which fillets widen. Added and
  cut extrusions also reach `OVERLAP_MM` back across their sketch plane: the fitted
  plane lies within the scan noise of the body's face, and a boss that only touches
  the body (or a pocket that leaves a skin) would not combine.

Order: bosses on the plane, then pockets, then the bosses standing in pockets (a
pocket would otherwise cut them away). Free profiles are left out: their outline is
better redrawn with the sketch tool.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature, Recognition
from m2c_kernel.recognition.outline import Outline
from m2c_kernel.recognition.planes import BasePlane

THROUGH_MARGIN_MM = 1.0
"""Through holes are cut this much beyond the far side."""
OVERLAP_MM = 0.5
"""Added and cut extrusions start this far behind their sketch plane."""
PLANE_TOLERANCE_FACTOR = 4.0
MIN_CORNER_MM = 0.01


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


def _unit(angle: float) -> FloatArray:
    return np.array([np.cos(angle), np.sin(angle)])


def _ccw(centre: FloatArray, start: FloatArray, end: FloatArray) -> bool:
    """Direction of the shorter arc from start to end around the centre."""
    a, b = start - centre, end - centre
    return bool(a[0] * b[1] - a[1] * b[0] > 0.0)


def _closed_chain(sketch: _Sketch, corners: Sequence[FloatArray], arcs: Sequence[Any]) -> str:
    """A closed loop: corner i to corner i + 1, straight or along arc i (centre, radius, ccw).

    Returns the loop id (its first entity); neighbouring entities are tangent.
    """
    ids = [sketch.point(corner) for corner in corners]
    entities: list[str] = []
    for i, arc in enumerate(arcs):
        start, end = ids[i], ids[(i + 1) % len(ids)]
        if arc is None:
            entities.append(sketch.line(start, end))
        else:
            centre, radius, ccw = arc
            entities.append(sketch.arc(start, end, centre, radius, ccw))
    for i, current in enumerate(entities):
        following = entities[(i + 1) % len(entities)]
        if (arcs[i] is None) != (arcs[(i + 1) % len(arcs)] is None):
            sketch.constrain("tangent", current, following)
    return entities[0]


def outline_loop(sketch: _Sketch, outline: Outline, shift: FloatArray) -> str | None:
    """Add a fitted outline to the sketch (moved by `shift`); returns its loop id."""
    p = outline.named()
    if outline.kind == "circle":
        centre = np.array([p["cx"], p["cy"]]) + shift
        return sketch.entity(
            "circle", center=[float(centre[0]), float(centre[1])], radius=p["radius"]
        )
    if outline.kind == "slot":
        return _slot(sketch, p, shift)
    if outline.kind == "roundedRect":
        return _rounded_rect(sketch, p, shift)
    if outline.kind == "ringSegment":
        return _ring_segment(sketch, p, shift)
    return None


def _slot(sketch: _Sketch, p: dict[str, float], shift: FloatArray) -> str:
    centre = np.array([p["cx"], p["cy"]]) + shift
    along, across = _unit(p["angle"]), _unit(p["angle"] + np.pi / 2.0)
    radius = p["width"] / 2.0
    half = max(p["length"] / 2.0 - radius, 1e-3)
    right, left = centre + half * along, centre - half * along
    corners = [
        right + radius * across,
        left + radius * across,
        left - radius * across,
        right - radius * across,
    ]
    arcs = [None, (left, radius, True), None, (right, radius, True)]
    loop = _closed_chain(sketch, corners, arcs)
    lines = [e["id"] for e in sketch.entities[-4:] if e["type"] == "line"]
    round_ends = [e["id"] for e in sketch.entities[-4:] if e["type"] == "arc"]
    sketch.constrain("parallel", *lines)
    sketch.constrain("equalRadius", *round_ends)
    return loop


def _rounded_rect(sketch: _Sketch, p: dict[str, float], shift: FloatArray) -> str:
    """Counter-clockwise from the end of the bottom side: corner arcs and sides."""
    centre = np.array([p["cx"], p["cy"]]) + shift
    x, y = _unit(p["angle"]), _unit(p["angle"] + np.pi / 2.0)
    hw, hh = p["width"] / 2.0, p["height"] / 2.0
    r = min(p["corner"], hw, hh)
    if r < MIN_CORNER_MM:
        sharp = [
            centre + sx * hw * x + sy * hh * y for sx, sy in ((1, -1), (1, 1), (-1, 1), (-1, -1))
        ]
        return _closed_chain(sketch, sharp, [None] * 4)
    corners: list[FloatArray] = []
    arcs: list[Any] = []
    # Corner centres bottom right, top right, top left, bottom left; each arc runs from
    # the side before the corner to the side after it.
    for sx, sy, before, after in (
        (1, -1, -y, x),
        (1, 1, x, y),
        (-1, 1, y, -x),
        (-1, -1, -x, -y),
    ):
        corner = centre + sx * (hw - r) * x + sy * (hh - r) * y
        corners += [corner + r * before, corner + r * after]
        arcs += [(corner, r, True), None]
    return _closed_chain(sketch, corners, arcs)


def _ring_segment(sketch: _Sketch, p: dict[str, float], shift: FloatArray) -> str:
    """A ring arm: outer and inner arc, two straight gap sides, rounded corners.

    Counter-clockwise: out along the start side, the outer arc to the end side, in
    along the end side, the inner arc back. A corner fillet of radius r is tangent to
    the gap side (its centre r from the side) and to the circle (its centre r inside
    the outer circle, r outside the inner one).
    """
    centre = np.array([p["cx"], p["cy"]]) + shift
    inner, outer = p["inner"], p["outer"]
    start, end = p["start"], p["start"] + p["sweep"]
    half_gap = p["gap"] / 2.0
    r = min(p["corner"], (outer - inner) / 2.0 - 1e-3)
    # Gap centre lines and their normals pointing into the arm.
    sides = ((_unit(start), _unit(start + np.pi / 2.0)), (_unit(end), _unit(end - np.pi / 2.0)))

    def at(side: int, radius: float, inset: float) -> FloatArray:
        """Point `inset` from the gap centre line and `radius` from the ring centre."""
        d, n = sides[side]
        t = np.sqrt(max(radius**2 - inset**2, 0.0))
        result: FloatArray = centre + t * d + inset * n
        return result

    if r < MIN_CORNER_MM:
        corners = [
            at(0, outer, half_gap),
            at(1, outer, half_gap),
            at(1, inner, half_gap),
            at(0, inner, half_gap),
        ]
        arcs = [(centre, outer, True), None, (centre, inner, False), None]
        return _closed_chain(sketch, corners, arcs)

    def fillet(
        side: int, radius: float, outside: bool
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Centre, tangent point on the gap side, tangent point on the circle."""
        _, n = sides[side]
        middle = at(side, radius - r if outside else radius + r, half_gap + r)
        on_side = middle - r * n
        towards = (middle - centre) / np.linalg.norm(middle - centre)
        on_circle = centre + radius * towards
        return middle, on_side, on_circle

    c1, s1, o1 = fillet(0, outer, True)
    c2, s2, o2 = fillet(1, outer, True)
    c3, s3, i3 = fillet(1, inner, False)
    c4, s4, i4 = fillet(0, inner, False)
    corners = [s1, o1, o2, s2, s3, i3, i4, s4]
    arcs = [
        (c1, r, _ccw(c1, s1, o1)),
        (centre, outer, True),
        (c2, r, _ccw(c2, o2, s2)),
        None,
        (c3, r, _ccw(c3, s3, i3)),
        (centre, inner, False),
        (c4, r, _ccw(c4, i4, s4)),
        None,
    ]
    return _closed_chain(sketch, corners, arcs)


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
        if feature.outline.kind == "profile" or (
            feature.relief.kind == "pocket" and target_body is None
        ):
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
    by_level: dict[float, list[int]] = {}
    for index in stage:
        by_level.setdefault(round(features[index].relief.level, 4), []).append(index)
    for level, indices in by_level.items():
        sketch = _Sketch()
        loops: dict[int, str] = {}
        for index in indices:
            loop = outline_loop(sketch, features[index].outline, shift)
            if loop is not None:
                loops[index] = loop
        if not loops:
            continue
        # Bosses rise along the normal, pockets sink against it: compare with the
        # scan halfway up the lowest of them, where every one has its wall.
        sign = 1.0 if features[indices[0]].relief.kind == "boss" else -1.0
        lowest = min(features[index].relief.height for index in loops)
        sketch_id = add(
            "sketch",
            {
                "section": {
                    "type": "planar",
                    "plane": {"type": "feature", "feature": plane_id},
                    "offset": level,
                    "sectionOffset": sign * lowest / 2.0,
                    "xDirection": _list(plane.x_axis),
                },
                "points": sketch.points,
                "entities": sketch.entities,
                "constraints": sketch.constraints,
            },
        )
        families: dict[tuple[object, ...], list[int]] = {}
        for index in loops:
            families.setdefault(_family(features[index]), []).append(index)
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


def _family(feature: Feature) -> tuple[object, ...]:
    """Features made alike: same kind, top, height, shape and size."""
    relief, outline = feature.relief, feature.outline
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
