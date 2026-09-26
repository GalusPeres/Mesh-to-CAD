"""Revolve: closed sketch profiles rotated about an axis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import BodyOperation, StandardAxis, feature_refs, not_implemented
from m2c_kernel.features.registry import Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class SketchLineAxis:
    type: Literal["sketchLine"] = "sketchLine"
    entity: str


@dataclass(frozen=True, kw_only=True)
class FeatureAxis:
    type: Literal["featureAxis"] = "featureAxis"
    feature: str


@dataclass(frozen=True, kw_only=True)
class GlobalAxis:
    type: Literal["globalAxis"] = "globalAxis"
    axis: StandardAxis


type RevolveAxis = SketchLineAxis | FeatureAxis | GlobalAxis


@dataclass(frozen=True, kw_only=True)
class RevolveParams:
    sketch: str
    loops: list[str] | None = None
    axis: RevolveAxis
    angle_deg: float = 360.0
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("revolve", params=RevolveParams)
class Revolve:
    @staticmethod
    def references(params: RevolveParams) -> Refs:
        axis = params.axis.feature if isinstance(params.axis, FeatureAxis) else None
        return Refs(
            features=feature_refs(params.sketch, axis), bodies=feature_refs(params.target_body)
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: RevolveParams) -> FeatureOutput:
        raise not_implemented("revolve")
