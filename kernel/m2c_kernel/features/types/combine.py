"""Combine: unite, subtract or intersect bodies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import feature_refs, not_implemented
from m2c_kernel.features.registry import Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


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
        raise not_implemented("combine")
