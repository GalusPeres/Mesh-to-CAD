"""Trim ("Körper teilen"): split a body by a plane or a freeform patch and keep one side.

`front` keeps the side the plane or patch normal points to, `back` the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.cad.references import reference_plane
from m2c_kernel.cad.trim import patch_face, trim_by_face, trim_by_plane
from m2c_kernel.codes.cad import ErrorCode, ProgressStage
from m2c_kernel.document.results import BodyUpdate, FeatureOutput
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import Refs, feature_type
from m2c_kernel.protocol.errors import KernelError

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext


@dataclass(frozen=True, kw_only=True)
class PlaneTool:
    type: Literal["plane"] = "plane"
    feature: str
    """A plane feature or an origin plane (`XY`, `YZ`, `XZ`)."""


@dataclass(frozen=True, kw_only=True)
class PatchTool:
    type: Literal["patch"] = "patch"
    feature: str
    """A freeform patch feature."""


type TrimTool = PlaneTool | PatchTool


@dataclass(frozen=True, kw_only=True)
class TrimParams:
    target_body: str
    tool: TrimTool
    keep: Literal["front", "back"] = "back"


@feature_type("trim", params=TrimParams)
class Trim:
    @staticmethod
    def references(params: TrimParams) -> Refs:
        return Refs(
            features=feature_refs(params.tool.feature), bodies=feature_refs(params.target_body)
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: TrimParams) -> FeatureOutput:
        body = ctx.body(params.target_body)
        tag = ctx.feature_id
        with ctx.job.native(ProgressStage.BOOLEAN):
            if isinstance(params.tool, PlaneTool):
                origin, normal = reference_plane(params.tool.feature, ctx.construction)
                result = trim_by_plane(body, origin, normal, params.keep, tag)
                trimmed, issues = result.body, result.issues
            else:
                surface = ctx.construction(params.tool.feature).surface
                if surface is None:
                    raise KernelError(ErrorCode.NOT_A_PATCH, {"feature": params.tool.feature})
                trimmed = trim_by_face(body, patch_face(surface), params.keep, tag)
                issues = ()
        return FeatureOutput(
            bodies=BodyUpdate(changed={params.target_body: trimmed}), issues=issues
        )
