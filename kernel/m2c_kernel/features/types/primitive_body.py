"""Primitive body: a solid cylinder, cone, sphere or torus from a fit feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import BodyOperation, feature_refs, not_implemented
from m2c_kernel.features.registry import Refs, feature_type

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class FacesExtent:
    """Extent along the axis from the fit's own triangles, plus a margin."""

    type: Literal["fromFaces"] = "fromFaces"
    margin: float = 0.0


@dataclass(frozen=True, kw_only=True)
class ManualExtent:
    type: Literal["manual"] = "manual"
    start: float
    length: float


type PrimitiveExtent = FacesExtent | ManualExtent


@dataclass(frozen=True, kw_only=True)
class PrimitiveBodyParams:
    fit: str
    extent: PrimitiveExtent = FacesExtent()
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("primitiveBody", params=PrimitiveBodyParams)
class PrimitiveBody:
    @staticmethod
    def references(params: PrimitiveBodyParams) -> Refs:
        return Refs(features=feature_refs(params.fit), bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: PrimitiveBodyParams) -> FeatureOutput:
        raise not_implemented("primitiveBody")
