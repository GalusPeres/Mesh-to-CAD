"""Combine: unite, subtract or intersect bodies.

The target body keeps its id. Tool bodies disappear unless `keep_tools` is set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.cad.booleans import boolean
from m2c_kernel.codes.cad import ErrorCode, ProgressStage
from m2c_kernel.document.results import BodyUpdate, FeatureOutput
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import Refs, feature_type
from m2c_kernel.protocol.errors import KernelError

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext


@dataclass(frozen=True, kw_only=True)
class CombineParams:
    target_body: str
    tools: list[str]
    operation: Literal["add", "cut", "intersect"]
    keep_tools: bool = False


@feature_type("combine", params=CombineParams)
class Combine:
    @staticmethod
    def references(params: CombineParams) -> Refs:
        return Refs(bodies=feature_refs(params.target_body, *params.tools))

    @staticmethod
    def evaluate(ctx: EvalContext, params: CombineParams) -> FeatureOutput:
        tools = list(dict.fromkeys(params.tools))
        if not tools:
            raise KernelError(ErrorCode.TOOLS_REQUIRED, {"operation": params.operation})
        if params.target_body in tools:
            raise KernelError(ErrorCode.TOOL_IS_TARGET, {"body": params.target_body})
        target = ctx.body(params.target_body)
        tool_bodies = [ctx.body(tool) for tool in tools]
        with ctx.job.native(ProgressStage.BOOLEAN):
            result = boolean(params.operation, target, tool_bodies)
        removed = () if params.keep_tools else tuple(tools)
        return FeatureOutput(
            bodies=BodyUpdate(changed={params.target_body: result.body}, removed=removed),
            issues=result.issues,
        )
