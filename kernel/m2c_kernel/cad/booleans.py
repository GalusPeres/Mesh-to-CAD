"""Boolean operations with the fuzzy policy of ARCHITECTURE.md 4.11.

Before the operation, tools whose planar faces lie within `SNAP_DISTANCE_MM` of
planar faces of the target are moved onto them when one translation satisfies
every such pair; that is the only variant that is both valid and clean for
near-coincident faces (`.work/research/algorithms-cad.md` 2.4). Then: fuzzy
value 1e-5 mm, non-destructive, history on, sequential (deterministic),
`SimplifyResult`. An invalid simplified result is healed with `ShapeFix_Shape`;
if that is still invalid the unsimplified result is used and the issue
`cad.splitFacesKept` reported. Face tags of all arguments are carried through
the history (`cad/tags.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepAlgoAPI_Common,
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    GeomAbs_Plane,
    List_TopoDS_Shape,
    ShapeFix_Shape,
    Standard_Failure,
    TopLoc_Location,
    TopoDS,
    TopoDS_Shape,
    gp_Trsf,
    gp_Vec,
)
from m2c_kernel.cad.tags import TagCollector, faces_of
from m2c_kernel.codes.cad import ErrorCode, IssueCode
from m2c_kernel.document.results import Body, Issue
from m2c_kernel.geometry import FloatArray
from m2c_kernel.protocol.errors import KernelError

type BooleanKind = Literal["add", "cut", "intersect"]

FUZZY_VALUE_MM = 1e-5
SNAP_DISTANCE_MM = 1e-3
"""Planar faces closer than this (and parallel) are treated as meant to coincide."""

_PARALLEL_SINE = 1e-9
_SNAP_RESIDUAL_MM = 1e-10

_BUILDERS = {"add": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "intersect": BRepAlgoAPI_Common}


@dataclass(frozen=True)
class BooleanResult:
    body: Body
    issues: tuple[Issue, ...] = ()


def boolean(kind: BooleanKind, target: Body, tools: list[Body]) -> BooleanResult:
    """`target` united with, reduced by or intersected with `tools`."""
    tools = [snap_to_target(target, tool) for tool in tools]
    builder = _BUILDERS[kind]()
    arguments = List_TopoDS_Shape()
    arguments.Append(target.shape)
    tool_list = List_TopoDS_Shape()
    for tool in tools:
        tool_list.Append(tool.shape)
    builder.SetArguments(arguments)
    builder.SetTools(tool_list)
    builder.SetFuzzyValue(FUZZY_VALUE_MM)
    builder.SetNonDestructive(True)
    builder.SetToFillHistory(True)
    builder.SetRunParallel(False)
    try:
        builder.Build()
        done = builder.IsDone()
    except Standard_Failure as failure:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": kind}, str(failure)) from None
    if not done:
        raise KernelError(ErrorCode.BOOLEAN_FAILED, {"operation": kind})

    raw = builder.Shape()
    _check_effect(kind, target, raw)
    sources = [target, *tools]
    try:
        builder.SimplifyResult(True, True)
        simplified = builder.Shape()
    except Standard_Failure:
        simplified = raw
    if check_solid(simplified).valid:
        return BooleanResult(_tagged(simplified, builder, sources))

    healed = heal(simplified)
    if healed is not None:
        collector = TagCollector(healed)
        collector.fill_by_proximity(sources)
        return BooleanResult(collector.body())
    return BooleanResult(_tagged(raw, None, sources), (Issue(IssueCode.SPLIT_FACES_KEPT),))


def _check_effect(kind: BooleanKind, target: Body, result: TopoDS_Shape) -> None:
    """Reject results that are empty, unchanged or fall apart (DESIGN.md 8.3)."""
    before = check_solid(target.shape).volume
    after = check_solid(result)
    tiny = 1e-7 * max(before, 1.0)
    if kind == "cut" and after.volume <= tiny:
        raise KernelError(ErrorCode.EMPTY_RESULT, {"operation": kind})
    if kind == "intersect" and after.volume <= tiny:
        raise KernelError(ErrorCode.NO_OVERLAP, {"operation": kind})
    if kind == "cut" and abs(after.volume - before) <= tiny:
        raise KernelError(ErrorCode.NO_OVERLAP, {"operation": kind})
    if after.solids > 1:
        code = ErrorCode.NO_OVERLAP if kind == "add" else ErrorCode.MULTIPLE_SOLIDS
        raise KernelError(code, {"operation": kind, "count": after.solids})


def heal(shape: TopoDS_Shape) -> TopoDS_Shape | None:
    """`ShapeFix_Shape` result if it is valid, else None."""
    fixer = ShapeFix_Shape(shape)
    fixer.SetPrecision(1e-6)
    fixer.SetMaxTolerance(1e-3)
    fixer.Perform()
    fixed = fixer.Shape()
    return fixed if check_solid(fixed).valid else None


def _tagged(shape: TopoDS_Shape, history: object | None, sources: list[Body]) -> Body:
    collector = TagCollector(shape)
    if history is not None:
        for source in sources:
            collector.carry(history, source)
    collector.fill_by_proximity(sources)
    return collector.body()


# --- Snapping of near-coincident planar faces ---------------------------------------------


def snap_to_target(target: Body, tool: Body) -> Body:
    """`tool`, translated so its near-coincident planar faces lie exactly on the target's.

    Every parallel pair of planar faces closer than `SNAP_DISTANCE_MM` (including
    pairs that already coincide) is a linear condition on the translation. The
    tool moves only if one translation meets all of them; otherwise it is left
    to the fuzzy boolean.
    """
    target_planes = _planes(target.shape)
    rows: list[FloatArray] = []
    offsets: list[float] = []
    for normal, offset in _planes(tool.shape):
        for target_normal, target_offset in target_planes:
            if np.linalg.norm(np.cross(normal, target_normal)) > _PARALLEL_SINE:
                continue
            aligned = offset if float(np.dot(normal, target_normal)) > 0 else -offset
            gap = target_offset - aligned
            if abs(gap) <= SNAP_DISTANCE_MM:
                rows.append(target_normal)
                offsets.append(gap)
    if not offsets or max(abs(gap) for gap in offsets) <= _SNAP_RESIDUAL_MM:
        return tool
    matrix = np.array(rows)
    wanted = np.array(offsets)
    translation, *_ = np.linalg.lstsq(matrix, wanted, rcond=None)
    if np.abs(matrix @ translation - wanted).max() > _SNAP_RESIDUAL_MM:
        return tool
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(*translation))
    return Body(tool.shape.Moved(TopLoc_Location(move)), tool.face_tags)


def _planes(shape: TopoDS_Shape) -> list[tuple[FloatArray, float]]:
    """Unit normal and offset (`normal . point`) of every planar face."""
    faces = faces_of(shape)
    planes = []
    for index in range(1, faces.Extent() + 1):
        surface = BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(index)))
        if surface.GetType() != GeomAbs_Plane:
            continue
        plane = surface.Plane()
        normal = np.array(plane.Axis().Direction().Coord())
        point = np.array(plane.Location().Coord())
        planes.append((normal, float(normal @ point)))
    return planes
