"""Loft: a solid through sections of the scan along an axis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from m2c_kernel.features.common import BodyOperation, StandardAxis, feature_refs, not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.protocol.wire import Range

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


@dataclass(frozen=True, kw_only=True)
class LoftParams:
    path: StandardAxis | str
    """A global axis or the id of a feature with an axis."""
    start: float
    end: float
    section_count: Annotated[int, Range(3, 64)] = 9
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("loft", params=LoftParams, reads=ReadSet(mesh=True))
class Loft:
    @staticmethod
    def references(params: LoftParams) -> Refs:
        return Refs(features=feature_refs(params.path), bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: LoftParams) -> FeatureOutput:
        raise not_implemented("loft")
