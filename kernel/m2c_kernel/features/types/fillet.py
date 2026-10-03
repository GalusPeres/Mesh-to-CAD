"""Fillet and chamfer: constant-size rounding or bevelling of body edges.

Edges are referenced by the face tags on both sides plus a point on the edge
(ARCHITECTURE.md 4.6), so the references still resolve after upstream changes
such as a new extrusion height. _Radius aus Scan_ is a helper of the tool, not
a parameter: the stored size is what the user accepted. Where the faces bend
tighter than the radius, the fillet narrows there and the feature says how far
(`cad.filletNarrowed`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from m2c_kernel.cad.edges import resolve_edges
from m2c_kernel.cad.fillet import fillet_edges
from m2c_kernel.codes.cad import IssueCode, ProgressStage
from m2c_kernel.document.results import BodyUpdate, FeatureOutput, Issue
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import Refs, feature_type
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.wire import Range

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext


@dataclass(frozen=True, kw_only=True)
class EdgeRef:
    """An edge identified by the tags of its two faces; `point` breaks ties.

    Face tags survive upstream parameter changes (see `document.results`), so the
    reference still resolves after, for example, an extrusion height changes.
    """

    faces: tuple[str, str]
    point: Vec3


@dataclass(frozen=True, kw_only=True)
class FilletParams:
    target_body: str
    edges: list[EdgeRef]
    mode: Literal["fillet", "chamfer"] = "fillet"
    size: Annotated[float, Range(0.001, None)]
    """Radius of a fillet, distance of a chamfer (mm)."""


@feature_type("fillet", params=FilletParams)
class Fillet:
    @staticmethod
    def references(params: FilletParams) -> Refs:
        return Refs(bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: FilletParams) -> FeatureOutput:
        body = ctx.body(params.target_body)
        edges = resolve_edges(body, [(edge.faces, edge.point) for edge in params.edges])
        with ctx.job.native(ProgressStage.FILLET):
            rounded = fillet_edges(body, edges, params.size, params.mode, ctx.feature_id)
        issues = (
            ()
            if rounded.smallest is None
            else (Issue(IssueCode.FILLET_NARROWED, {"smallest": round(rounded.smallest, 3)}),)
        )
        return FeatureOutput(
            bodies=BodyUpdate(changed={params.target_body: rounded.body}), issues=issues
        )
