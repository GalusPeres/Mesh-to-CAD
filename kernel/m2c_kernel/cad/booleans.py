"""Boolean operations with the fuzzy policy of ARCHITECTURE.md 4.11.

Fuzzy value 1e-5 mm, non-destructive, history on, sequential (deterministic),
then `SimplifyResult`. An invalid simplified result is healed with
`ShapeFix_Shape`; if that is still invalid the unsimplified result is used and
the issue `cad.splitFacesKept` reported. Face tags of all arguments are carried
through the history (`cad/tags.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Common,
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    List_TopoDS_Shape,
    ShapeFix_Shape,
    Standard_Failure,
    TopoDS_Shape,
)
from m2c_kernel.cad.tags import TagCollector
from m2c_kernel.codes.cad import ErrorCode, IssueCode
from m2c_kernel.document.results import Body, Issue
from m2c_kernel.protocol.errors import KernelError

type BooleanKind = Literal["add", "cut", "intersect"]

FUZZY_VALUE_MM = 1e-5

_BUILDERS = {"add": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "intersect": BRepAlgoAPI_Common}


@dataclass(frozen=True)
class BooleanResult:
    body: Body
    issues: tuple[Issue, ...] = ()


def boolean(kind: BooleanKind, target: Body, tools: list[Body]) -> BooleanResult:
    """`target` united with, reduced by or intersected with `tools`."""
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
    if kind != "add" and check_solid(raw).volume <= 0.0:
        raise KernelError(ErrorCode.EMPTY_RESULT, {"operation": kind})
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
