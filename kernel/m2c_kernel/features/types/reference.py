"""Reference geometry: planes and axes constructed from other features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import StandardPlane, feature_refs, not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class OffsetPlane:
    type: Literal["offsetPlane"] = "offsetPlane"
    plane: StandardPlane | str
    offset: float


@dataclass(frozen=True, kw_only=True)
class MidPlane:
    type: Literal["midPlane"] = "midPlane"
    first: str
    second: str


@dataclass(frozen=True, kw_only=True)
class PlaneThroughAxis:
    """A plane containing a fitted axis, rotated by `angle_deg` about it (for revolve sketches)."""

    type: Literal["planeThroughAxis"] = "planeThroughAxis"
    axis: str
    angle_deg: float = 0.0


@dataclass(frozen=True, kw_only=True)
class AxisFromPlanes:
    type: Literal["axisFromPlanes"] = "axisFromPlanes"
    first: str
    second: str


type ReferenceDefinition = OffsetPlane | MidPlane | PlaneThroughAxis | AxisFromPlanes


@dataclass(frozen=True, kw_only=True)
class ReferenceParams:
    definition: ReferenceDefinition


@feature_type("reference", params=ReferenceParams, reads=ReadSet(alignment=True))
class Reference:
    @staticmethod
    def references(params: ReferenceParams) -> Refs:
        definition = params.definition
        if isinstance(definition, OffsetPlane):
            return Refs(features=feature_refs(definition.plane))
        if isinstance(definition, PlaneThroughAxis):
            return Refs(features=feature_refs(definition.axis))
        return Refs(features=feature_refs(definition.first, definition.second))

    @staticmethod
    def evaluate(ctx: EvalContext, params: ReferenceParams) -> FeatureOutput:
        raise not_implemented("reference")
