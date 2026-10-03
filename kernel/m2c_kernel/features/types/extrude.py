"""Extrude: closed sketch profiles swept along the sketch normal.

`direction` picks the side: `normal` extrudes `forward` along the sketch normal
and `backward` against it, `reversed` swaps the sides, and `symmetric` extrudes
`forward` as the total length centred on the sketch plane. `toPlane` ends the
extrusion at a plane feature (or origin plane) shifted by `offset` along its
normal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from m2c_kernel.cad.operations import solid_output
from m2c_kernel.cad.profiles import sketch_profiles
from m2c_kernel.cad.references import reference_plane
from m2c_kernel.cad.solids import extrude_islands, extrude_to_plane_islands
from m2c_kernel.codes.cad import ErrorCode, ProgressStage
from m2c_kernel.features.common import BodyOperation, feature_refs
from m2c_kernel.features.registry import Refs, feature_type
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import Range

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import Body, FeatureOutput


@dataclass(frozen=True, kw_only=True)
class DistanceExtent:
    type: Literal["distance"] = "distance"
    forward: Annotated[float, Range(0.0, None)]
    backward: Annotated[float, Range(0.0, None)] = 0.0


@dataclass(frozen=True, kw_only=True)
class ToPlaneExtent:
    type: Literal["toPlane"] = "toPlane"
    feature: str
    """A plane feature or an origin plane (`XY`, `YZ`, `XZ`)."""
    offset: float = 0.0


type ExtrudeExtent = DistanceExtent | ToPlaneExtent


@dataclass(frozen=True, kw_only=True)
class ExtrudeParams:
    sketch: str
    loops: list[str] | None = None
    """Loop ids of the sketch to use; None uses every closed loop."""
    direction: Literal["normal", "reversed", "symmetric"] = "normal"
    extent: ExtrudeExtent
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("extrude", params=ExtrudeParams)
class Extrude:
    @staticmethod
    def references(params: ExtrudeParams) -> Refs:
        extent = params.extent
        plane = extent.feature if isinstance(extent, ToPlaneExtent) else None
        return Refs(
            features=feature_refs(params.sketch, plane),
            bodies=feature_refs(params.target_body) if params.operation != "newBody" else (),
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: ExtrudeParams) -> FeatureOutput:
        sketch = ctx.sketch(params.sketch)
        profiles = sketch_profiles(sketch, params.loops)
        normal = sketch.frame.normal if params.direction != "reversed" else -sketch.frame.normal
        extent = params.extent
        with ctx.job.native(ProgressStage.MODELLING):
            islands: list[Body]
            if isinstance(extent, DistanceExtent):
                forward, backward = extent.forward, extent.backward
                if params.direction == "symmetric":
                    forward = backward = extent.forward / 2
                islands = extrude_islands(profiles, normal, forward, backward, ctx.feature_id)
            else:
                if params.direction == "symmetric":
                    raise KernelError(ErrorCode.SYMMETRIC_TO_PLANE)
                origin, plane_normal = reference_plane(extent.feature, ctx.construction)
                shifted = origin + plane_normal * extent.offset
                islands = extrude_to_plane_islands(
                    profiles, normal, shifted, plane_normal, ctx.feature_id
                )
            return solid_output(
                ctx.feature_id, params.operation, params.target_body, islands, ctx.body
            )
