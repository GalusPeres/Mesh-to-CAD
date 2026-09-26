"""Trim: cut a body with a plane or a freeform patch and keep one side."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import feature_refs, not_implemented
from m2c_kernel.features.registry import Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class TrimParams:
    target_body: str
    tool: str
    """A feature that provides a plane or a freeform patch."""
    keep: Literal["front", "back"] = "back"


@feature_type("trim", params=TrimParams)
class Trim:
    @staticmethod
    def references(params: TrimParams) -> Refs:
        return Refs(features=feature_refs(params.tool), bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: TrimParams) -> FeatureOutput:
        raise not_implemented("trim")
