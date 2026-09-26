"""Extrude: closed sketch profiles swept along the sketch normal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import BodyOperation, feature_refs, not_implemented
from m2c_kernel.features.registry import Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class DistanceExtent:
    type: Literal["distance"] = "distance"
    forward: float
    backward: float = 0.0


@dataclass(frozen=True, kw_only=True)
class ToPlaneExtent:
    type: Literal["toPlane"] = "toPlane"
    feature: str
    offset: float = 0.0


type ExtrudeExtent = DistanceExtent | ToPlaneExtent


@dataclass(frozen=True, kw_only=True)
class ExtrudeParams:
    sketch: str
    loops: list[str] | None = None
    """Loop ids to extrude; None extrudes every closed loop."""
    direction: Literal["normal", "reversed", "symmetric"] = "normal"
    extent: ExtrudeExtent
    taper_deg: float = 0.0
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("extrude", params=ExtrudeParams)
class Extrude:
    @staticmethod
    def references(params: ExtrudeParams) -> Refs:
        extent = params.extent
        plane = extent.feature if isinstance(extent, ToPlaneExtent) else None
        return Refs(
            features=feature_refs(params.sketch, plane), bodies=feature_refs(params.target_body)
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: ExtrudeParams) -> FeatureOutput:
        raise not_implemented("extrude")
