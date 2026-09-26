"""Fillet and chamfer: constant-size rounding or bevelling of body edges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from m2c_kernel.features.common import feature_refs, not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.geometry import Vec3

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput


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
    size: float
    size_from_scan: bool = False
    """Take the radius from a cylinder fitted to the scan along the picked edges."""


@feature_type("fillet", params=FilletParams, reads=ReadSet(mesh=True))
class Fillet:
    @staticmethod
    def references(params: FilletParams) -> Refs:
        return Refs(bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: FilletParams) -> FeatureOutput:
        raise not_implemented("fillet")
