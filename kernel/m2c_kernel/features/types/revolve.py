"""Revolve: closed sketch profiles rotated about an axis in the sketch plane.

The axis is a line of the sketch, the axis of a fit or reference feature, or a
global axis. Angles are counter-clockwise about the axis direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from m2c_kernel.cad.operations import solid_output
from m2c_kernel.cad.profiles import sketch_line, sketch_profiles
from m2c_kernel.cad.references import reference_axis
from m2c_kernel.cad.solids import revolve_islands
from m2c_kernel.codes.cad import ProgressStage
from m2c_kernel.features.common import BodyOperation, StandardAxis, feature_refs
from m2c_kernel.features.registry import Refs, feature_type
from m2c_kernel.protocol.wire import Range

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
    """Loop ids of the sketch to use; None uses every closed loop."""
    axis: RevolveAxis
    angle_deg: Annotated[float, Range(0.0, 360.0)] = 360.0
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@feature_type("revolve", params=RevolveParams)
class Revolve:
    @staticmethod
    def references(params: RevolveParams) -> Refs:
        axis = params.axis.feature if isinstance(params.axis, FeatureAxis) else None
        return Refs(
            features=feature_refs(params.sketch, axis),
            bodies=feature_refs(params.target_body) if params.operation != "newBody" else (),
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: RevolveParams) -> FeatureOutput:
        sketch = ctx.sketch(params.sketch)
        profiles = sketch_profiles(sketch, params.loops)
        match params.axis:
            case SketchLineAxis(entity=entity):
                point, direction = sketch_line(sketch, entity)
            case FeatureAxis(feature=feature):
                point, direction = reference_axis(feature, ctx.construction)
            case GlobalAxis(axis=axis):
                point, direction = reference_axis(axis, ctx.construction)
        with ctx.job.native(ProgressStage.MODELLING):
            islands = revolve_islands(
                profiles, sketch.frame, point, direction, params.angle_deg, ctx.feature_id
            )
            return solid_output(
                ctx.feature_id, params.operation, params.target_body, islands, ctx.body
            )
