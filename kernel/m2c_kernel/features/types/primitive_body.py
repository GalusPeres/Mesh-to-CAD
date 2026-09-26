"""Primitive body: a solid cylinder, cone, sphere or torus from a fit feature.

Spheres and tori are closed. Cylinders and cones are cut to an extent along
their axis: either the extent of the scan surface the fit describes plus a
margin (`region`), or `manual` values. Manual positions are measured along the
axis from the foot of the perpendicular dropped from the part origin, so for an
axis parallel to Z the start is the Z coordinate.

The scan surface of a fit is the set of scan vertices within the project
tolerance of the fitted surface, inside the range the fit covers (its
construction display, which spans the fitted triangles plus a small margin).
The seam of the curved face is put on the side the scan surface does not cover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

import numpy as np

from m2c_kernel.cad.operations import solid_output
from m2c_kernel.cad.solids import cone, cylinder, sphere, torus
from m2c_kernel.codes.cad import ErrorCode, ProgressStage
from m2c_kernel.features.common import BodyOperation, feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.api import Cone, Cylinder, Primitive, Sphere, Torus, signed_distance
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import Range

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import Body, FeatureOutput

MIN_SURFACE_POINTS = 20


@dataclass(frozen=True, kw_only=True)
class RegionExtent:
    """Extent along the axis from the scan surface of the fit, plus a margin at both ends."""

    type: Literal["region"] = "region"
    margin: Annotated[float, Range(0.0, None)] = 0.0


@dataclass(frozen=True, kw_only=True)
class ManualExtent:
    type: Literal["manual"] = "manual"
    start: float
    length: Annotated[float, Range(0.0, None)]


type PrimitiveExtent = RegionExtent | ManualExtent


@dataclass(frozen=True, kw_only=True)
class PrimitiveBodyParams:
    fit: str
    extent: PrimitiveExtent = RegionExtent()
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@dataclass(frozen=True)
class _Span:
    """Axial range [start, end] relative to `origin` along `axis`, and the seam direction."""

    origin: FloatArray
    axis: FloatArray
    start: float
    end: float
    seam: FloatArray | None


@feature_type(
    "primitiveBody", params=PrimitiveBodyParams, reads=ReadSet(mesh=True, settings=("tolerance",))
)
class PrimitiveBody:
    @staticmethod
    def references(params: PrimitiveBodyParams) -> Refs:
        return Refs(
            features=feature_refs(params.fit),
            bodies=feature_refs(params.target_body) if params.operation != "newBody" else (),
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: PrimitiveBodyParams) -> FeatureOutput:
        primitive = ctx.construction(params.fit).primitive
        tag = ctx.feature_id
        body: Body
        match primitive:
            case Sphere(center=center, radius=radius):
                with ctx.job.native(ProgressStage.MODELLING):
                    body = sphere(np.asarray(center), radius, tag)
            case Torus(center=center, axis=axis, major_radius=major, minor_radius=minor):
                centre, direction = np.asarray(center, dtype=np.float64), unit(axis)
                seam = _seam_if_scanned(ctx, params.fit, primitive, centre, direction)
                with ctx.job.native(ProgressStage.MODELLING):
                    body = torus(centre, direction, major, minor, tag, seam)
            case Cylinder(origin=origin, axis=axis, radius=radius):
                span = _span(
                    ctx, params, primitive, np.asarray(origin, dtype=np.float64), unit(axis)
                )
                base = span.origin + span.start * span.axis
                with ctx.job.native(ProgressStage.MODELLING):
                    body = cylinder(base, span.axis, radius, span.end - span.start, tag, span.seam)
            case Cone(apex=apex, axis=axis, half_angle=half_angle):
                span = _span(ctx, params, primitive, np.asarray(apex, dtype=np.float64), unit(axis))
                start = max(span.start, 0.0)  # the cone does not continue behind its apex
                slope = float(np.tan(half_angle))
                base = span.origin + start * span.axis
                with ctx.job.native(ProgressStage.MODELLING):
                    body = cone(
                        base,
                        span.axis,
                        start * slope,
                        span.end * slope,
                        span.end - start,
                        tag,
                        span.seam,
                    )
            case _:
                raise KernelError(ErrorCode.UNSUPPORTED_FIT, {"feature": params.fit})
        with ctx.job.native(ProgressStage.BOOLEAN):
            return solid_output(tag, params.operation, params.target_body, body, ctx.body)


def _span(
    ctx: EvalContext,
    params: PrimitiveBodyParams,
    primitive: Primitive,
    origin: FloatArray,
    axis: FloatArray,
) -> _Span:
    extent = params.extent
    if isinstance(extent, ManualExtent):
        # Positions count from the foot of the perpendicular from the part origin.
        foot_offset = float(-origin @ axis)
        start = foot_offset + extent.start
        return _Span(origin, axis, start, start + extent.length, None)
    points = _surface_points(ctx, params.fit, primitive, origin, axis)
    heights = _heights_on_surface(primitive, points, origin, axis)
    return _Span(
        origin,
        axis,
        float(heights.min()) - extent.margin,
        float(heights.max()) + extent.margin,
        _seam(points, origin, axis),
    )


def _heights_on_surface(
    primitive: Primitive, points: FloatArray, origin: FloatArray, axis: FloatArray
) -> FloatArray:
    """Axial coordinates of the points after moving them onto the surface along its normal.

    Scan noise lies along the surface normal; on a cone the normal has an axial part,
    so the raw extremes would overshoot the extent by the noise.
    """
    relative = points - origin
    heights: FloatArray = relative @ axis
    if isinstance(primitive, Cone):
        radial = np.linalg.norm(relative - np.outer(heights, axis), axis=1)
        cos, sin = np.cos(primitive.half_angle), np.sin(primitive.half_angle)
        heights = (heights * cos + radial * sin) * cos
    return heights


def _surface_points(
    ctx: EvalContext, fit_id: str, primitive: Primitive, origin: FloatArray, axis: FloatArray
) -> FloatArray:
    """Scan vertices on the fitted surface inside the axial range the fit covers."""
    window = [
        source.positions
        for source in ctx.output(fit_id).display
        if source.kind == "mesh" and source.style == "construction"
    ]
    if not window:
        raise KernelError(ErrorCode.NO_EXTENT, {"feature": fit_id})
    covered = (window[0] - origin) @ axis
    vertices = ctx.mesh.vertices
    tolerance = ctx.settings.tolerance
    heights = (vertices - origin) @ axis
    inside = (heights >= covered.min() - tolerance) & (heights <= covered.max() + tolerance)
    candidates = vertices[inside]
    near = np.abs(signed_distance(primitive, candidates)) <= tolerance
    points: FloatArray = candidates[near]
    if len(points) < MIN_SURFACE_POINTS:
        raise KernelError(ErrorCode.NO_EXTENT, {"feature": fit_id})
    return points


def _seam_if_scanned(
    ctx: EvalContext, fit_id: str, primitive: Primitive, origin: FloatArray, axis: FloatArray
) -> FloatArray | None:
    """Seam direction of a closed primitive; without scan support the default seam is fine."""
    try:
        points = _surface_points(ctx, fit_id, primitive, origin, axis)
    except KernelError:
        return None
    return _seam(points, origin, axis)


def _seam(points: FloatArray, origin: FloatArray, axis: FloatArray) -> FloatArray | None:
    """Direction away from the covered part of the surface (for the seam of the curved face)."""
    relative = points - origin
    radial = relative - np.outer(relative @ axis, axis)
    lengths = np.linalg.norm(radial, axis=1)
    radial = radial[lengths > 1e-9] / lengths[lengths > 1e-9, None]
    if len(radial) == 0:
        return None
    mean = radial.mean(axis=0)
    if np.linalg.norm(mean) > 0.2:
        return -unit(mean)
    # Evenly covered all around: use the principal direction, which is reproducible.
    _values, vectors = np.linalg.eigh(radial.T @ radial)
    direction: FloatArray = vectors[:, -1]
    return direction
