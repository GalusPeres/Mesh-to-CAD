"""Sketch entities of an outline shape, with the constraints and snaps that keep it one.

A designed shape (`shape_intent.Design`) becomes a closed chain of lines and arcs in
the fixed entity order of `SketchShape`: tangent junctions, equal corner radii,
parallel or axis-parallel sides, concentric ring arcs. Its kept design values become
snaps (radius, line length, direction), so refits hold them and the user can remove
them like any other snapped value.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from m2c_kernel.sketch.model import (
    Arc,
    Circle,
    Constraint,
    FloatArray,
    Line,
    Point,
    Shape,
    WorkSketch,
    line_through,
)
from m2c_kernel.sketch.params import ShapeKind, SketchSnap
from m2c_kernel.sketch.shape_intent import Design
from m2c_kernel.sketch.shapes import ShapeFit

MIN_CORNER = 0.05
"""Corner radii below this (mm) are sharp corners."""


@dataclass(frozen=True)
class BuiltShape:
    shape: Shape
    constraints: list[Constraint]
    snaps: list[SketchSnap]


type IdTaker = Callable[[str], str]


@dataclass(frozen=True)
class _Piece:
    """One entity of a closed chain, from junction `i` to junction `i + 1`."""

    center: FloatArray | None = None
    radius: float = 0.0
    ccw: bool = True

    @property
    def is_line(self) -> bool:
        return self.center is None


def _chain(
    sketch: WorkSketch, take: IdTaker, junctions: Sequence[FloatArray], pieces: Sequence[_Piece]
) -> list[str]:
    """Add a closed chain of lines and arcs; returns the entity ids in order."""
    point_ids = [take("p") for _ in junctions]
    for pid, xy in zip(point_ids, junctions, strict=True):
        sketch.points[pid] = Point(pid, np.asarray(xy, dtype=np.float64))
    ids = []
    for k, piece in enumerate(pieces):
        start, end = point_ids[k], point_ids[(k + 1) % len(point_ids)]
        eid = take("e")
        if piece.center is None:
            angle, offset = line_through(sketch.xy(start), sketch.xy(end))
            sketch.entities[eid] = Line(eid, angle, offset, start, end)
        else:
            sketch.entities[eid] = Arc(
                eid, piece.center.copy(), piece.radius, piece.ccw, start, end
            )
        ids.append(eid)
    return ids


def _frame(shape: ShapeFit) -> tuple[FloatArray, FloatArray, FloatArray]:
    angle = shape["angle"]
    return (
        shape.center,
        np.array([math.cos(angle), math.sin(angle)]),
        np.array([-math.sin(angle), math.cos(angle)]),
    )


def _slot(sketch: WorkSketch, take: IdTaker, shape: ShapeFit) -> list[str]:
    c, d, n = _frame(shape)
    r = shape["width"] / 2.0
    a = shape["length"] / 2.0 - r
    junctions = [c - a * d - r * n, c + a * d - r * n, c + a * d + r * n, c - a * d + r * n]
    pieces = [_Piece(), _Piece(c + a * d, r), _Piece(), _Piece(c - a * d, r)]
    return _chain(sketch, take, junctions, pieces)


def _rounded_rect(sketch: WorkSketch, take: IdTaker, shape: ShapeFit) -> list[str]:
    c, d, n = _frame(shape)
    hl, hw, r = shape["length"] / 2.0, shape["width"] / 2.0, shape["corner"]
    if r < MIN_CORNER:
        corners = [
            c - hl * d - hw * n,
            c + hl * d - hw * n,
            c + hl * d + hw * n,
            c - hl * d + hw * n,
        ]
        return _chain(sketch, take, corners, [_Piece()] * 4)
    a, b = hl - r, hw - r
    # Counter-clockwise from the start of the bottom side; every side is followed by
    # the corner after it.
    junctions = [
        c - a * d - hw * n,
        c + a * d - hw * n,
        c + hl * d - b * n,
        c + hl * d + b * n,
        c + a * d + hw * n,
        c - a * d + hw * n,
        c - hl * d + b * n,
        c - hl * d - b * n,
    ]
    centres = [c + a * d - b * n, c + a * d + b * n, c - a * d + b * n, c - a * d - b * n]
    pieces = [p for centre in centres for p in (_Piece(), _Piece(centre, r))]
    return _chain(sketch, take, junctions, pieces)


def _ring_arm(sketch: WorkSketch, take: IdTaker, shape: ShapeFit) -> list[str]:
    c = shape.center
    inner, outer, gap, r = shape["inner"], shape["outer"], shape["gap"], shape["corner"]
    a0, a1 = shape["start"], shape["start"] + shape["sweep"]
    u0, u1 = np.array([math.cos(a0), math.sin(a0)]), np.array([math.cos(a1), math.sin(a1)])
    n0, n1 = np.array([-u0[1], u0[0]]), np.array([u1[1], -u1[0]])
    """Inward normals of the two end lines (towards the arm)."""
    r = r if r >= MIN_CORNER else 0.0

    def corner(u: FloatArray, n: FloatArray, radius: float) -> FloatArray:
        along = math.sqrt(max(radius**2 - (gap + r) ** 2, 0.0))
        return c + along * u + (gap + r) * n

    def on_circle(centre: FloatArray, radius: float) -> FloatArray:
        direction = centre - c
        return c + radius * direction / max(float(np.linalg.norm(direction)), 1e-12)

    out0, out1 = corner(u0, n0, outer - r), corner(u1, n1, outer - r)
    in1, in0 = corner(u1, n1, inner + r), corner(u0, n0, inner + r)
    if r == 0.0:
        junctions = [out0, out1, in1, in0]
        pieces = [_Piece(c, outer), _Piece(), _Piece(c, inner, ccw=False), _Piece()]
        return _chain(sketch, take, junctions, pieces)
    junctions = [
        on_circle(out0, outer),
        on_circle(out1, outer),
        out1 - r * n1,
        in1 - r * n1,
        on_circle(in1, inner),
        on_circle(in0, inner),
        in0 - r * n0,
        out0 - r * n0,
    ]
    pieces = [
        _Piece(c, outer),
        _Piece(out1, r),
        _Piece(),
        _Piece(in1, r),
        _Piece(c, inner, ccw=False),
        _Piece(in0, r),
        _Piece(),
        _Piece(out0, r),
    ]
    return _chain(sketch, take, junctions, pieces)


def _constraints(
    sketch: WorkSketch, kind: ShapeKind, ids: list[str], axis: bool
) -> list[Constraint]:
    entities = [sketch.entities[e] for e in ids]
    result = [
        Constraint("tangent", (a.id, b.id))
        for a, b in zip(entities, entities[1:] + entities[:1], strict=True)
        if not (isinstance(a, Line) and isinstance(b, Line))
    ]
    lines = [e.id for e in entities if isinstance(e, Line)]
    middle = ids[len(ids) // 2]
    if kind == "ringArm":
        result.append(Constraint("concentric", (ids[0], middle)))
        corners = [e.id for e in entities if isinstance(e, Arc) and e.id not in (ids[0], middle)]
    else:
        corners = [e.id for e in entities if isinstance(e, Arc)]
        if axis:
            for line in lines:
                carrier = sketch.entities[line]
                assert isinstance(carrier, Line)
                horizontal = abs(math.sin(carrier.angle)) > abs(math.cos(carrier.angle))
                result.append(Constraint("horizontal" if horizontal else "vertical", (line,)))
        elif len(lines) == 2:
            result.append(Constraint("parallel", (lines[0], lines[1])))
        else:
            result += [
                Constraint("parallel", (lines[0], lines[2])),
                Constraint("parallel", (lines[1], lines[3])),
                Constraint("perpendicular", (lines[0], lines[1])),
            ]
    result += [Constraint("equalRadius", pair) for pair in itertools.pairwise(corners)]
    return result


def _snap(entity: str, kind: str, value: float, measured: float) -> SketchSnap:
    return SketchSnap(
        id=f"{entity}:{kind}",
        entity=entity,
        kind=kind,  # type: ignore[arg-type]
        value=value,
        measured=measured,
        uncertainty=0.0,
    )


def _snaps(sketch: WorkSketch, kind: ShapeKind, ids: list[str], design: Design) -> list[SketchSnap]:
    """Snaps for the kept design values (radius, line lengths, directions)."""
    shape, measured, kept = design.shape, design.measured, design.snapped
    out: list[SketchSnap] = []
    entities = [sketch.entities[e] for e in ids]
    arcs = [e for e in entities if isinstance(e, Arc | Circle)]
    lines = [e for e in entities if isinstance(e, Line)]
    if kind == "circle" and "diameter" in kept:
        out.append(_snap(ids[0], "radius", shape["radius"], measured["radius"]))
    if kind == "slot" and "width" in kept:
        out += [_snap(a.id, "radius", shape["width"] / 2, measured["width"] / 2) for a in arcs]
        if "length" in kept:
            value = shape["length"] - shape["width"]
            out.append(_snap(lines[0].id, "length", value, measured["length"] - measured["width"]))
    if kind == "roundedRect" and "corner" in kept:
        r, mr = shape["corner"], measured["corner"]
        out += [_snap(a.id, "radius", r, mr) for a in arcs]
        for line, name in zip(lines[:2], ("length", "width"), strict=False):
            if name in kept:
                out.append(_snap(line.id, "length", shape[name] - 2 * r, measured[name] - 2 * mr))
    if kind == "ringArm":
        for arc, name in ((arcs[0], "outer"), (sketch.entities[ids[len(ids) // 2]], "inner")):
            if name in kept:
                out.append(_snap(arc.id, "radius", shape[name], measured[name]))
        if "corner" in kept:
            corners = [a for a in arcs if a.id not in (ids[0], ids[len(ids) // 2])]
            out += [_snap(a.id, "radius", shape["corner"], measured["corner"]) for a in corners]
    if kind in ("slot", "roundedRect") and "angle" in kept and not _axis(shape):
        direction = math.degrees(shape["angle"]) % 180.0
        out.append(_snap(lines[0].id, "angle", direction, math.degrees(measured["angle"]) % 180.0))
    if kind == "ringArm" and {"start", "sweep"} <= kept:
        for line, angle, raw in (
            (lines[0], shape["start"] + shape["sweep"], measured["start"] + measured["sweep"]),
            (lines[-1], shape["start"], measured["start"]),
        ):
            out.append(
                _snap(line.id, "angle", math.degrees(angle) % 180.0, math.degrees(raw) % 180.0)
            )
    return out


def _axis(shape: ShapeFit) -> bool:
    """Sides parallel to the sketch axes."""
    return abs(math.sin(2.0 * shape["angle"])) < 1e-9


def build(sketch: WorkSketch, take: IdTaker, design: Design) -> BuiltShape:
    """Add the entities of a designed shape to the sketch."""
    shape, kind = design.shape, design.shape.kind
    if kind == "circle":
        eid = take("e")
        sketch.entities[eid] = Circle(eid, shape.center, shape["radius"])
        ids = [eid]
    elif kind == "slot":
        ids = _slot(sketch, take, shape)
    elif kind == "roundedRect":
        ids = _rounded_rect(sketch, take, shape)
    else:
        ids = _ring_arm(sketch, take, shape)
    axis = kind in ("slot", "roundedRect") and "angle" in design.snapped and _axis(shape)
    constraints = _constraints(sketch, kind, ids, axis) if kind != "circle" else []
    if design.concentric is not None and design.concentric in sketch.entities:
        constraints.append(Constraint("concentric", (design.concentric, ids[0])))
    built = Shape(take("s"), kind, tuple(ids))
    sketch.shapes.append(built)
    return BuiltShape(built, constraints, _snaps(sketch, kind, ids, design))


def sizes(sketch: WorkSketch, shape: Shape) -> dict[str, float]:
    """Design sizes of a shape read from its entities (see `shape_intent.SIZES`)."""
    entities = [sketch.entities[e] for e in shape.entities]
    rounds = [e for e in entities if isinstance(e, Arc | Circle)]
    lines = [e for e in entities if isinstance(e, Line)]

    def length(line: Line) -> float:
        return float(np.linalg.norm(sketch.xy(line.end) - sketch.xy(line.start)))

    match shape.kind:
        case "circle":
            return {"diameter": 2.0 * rounds[0].radius}
        case "slot":
            r = rounds[0].radius
            return {"width": 2.0 * r, "length": length(lines[0]) + 2.0 * r}
        case "roundedRect":
            r = rounds[0].radius if rounds else 0.0
            sides = sorted((length(lines[0]), length(lines[1])), reverse=True)
            return {"corner": r, "length": sides[0] + 2 * r, "width": sides[1] + 2 * r}
        case "ringArm":
            middle = sketch.entities[shape.entities[len(shape.entities) // 2]]
            assert isinstance(middle, Arc)
            corners = [e for e in rounds if e.id not in (shape.entities[0], middle.id)]
            return {
                "outer": rounds[0].radius,
                "inner": middle.radius,
                "corner": corners[0].radius if corners else 0.0,
            }
    return {}
