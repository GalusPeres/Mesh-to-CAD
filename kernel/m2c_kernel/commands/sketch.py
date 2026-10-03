"""Section sketches: cut the scan, fit a sketch, fit single entities.

All three methods run in the tool's lane and never commit; the sketch tool
commits the finished sketch with `doc.apply`. They read the current document:
the aligned scan and the planes and axes of earlier features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.document.results import Construction
from m2c_kernel.geometry import Vec3, vec3
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, F64Array
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.sketch.api import (
    EntityFit,
    FitResult,
    SectionGeometry,
    auto_fit,
    cut,
    fit_entity,
    fit_tolerance,
    section_geometry,
)
from m2c_kernel.sketch.autofit import section_noise, suggested_tolerance
from m2c_kernel.sketch.params import SketchParams, SketchSection
from m2c_kernel.sketch.section import Section

MAX_FOLDED_DISPLAY = 20_000


@dataclass(frozen=True)
class SketchFrame:
    """The sketch plane in part coordinates; sketch (u, v) maps to origin + u x + v y."""

    origin: Vec3
    x_dir: Vec3
    y_dir: Vec3
    normal: Vec3
    base_origin: Vec3
    """Source plane origin before the sketch offset (anchor of the offset handle)."""
    offset_direction: Vec3
    rotational: bool


@dataclass(frozen=True)
class EntityFitInfo:
    entity: str
    points: int
    max_distance: float | None
    rms: float | None
    share: float | None
    passed: bool | None


@dataclass(frozen=True)
class ProfileState:
    closed: bool
    loops: list[str]
    open_entities: list[str]
    gaps: list[tuple[float, float]]
    """Chain ends in sketch coordinates."""
    branch_points: list[str]


def _frame(geometry: SectionGeometry) -> SketchFrame:
    frame = geometry.frame
    return SketchFrame(
        origin=vec3(frame.origin),
        x_dir=vec3(frame.x_dir),
        y_dir=vec3(frame.y_dir),
        normal=vec3(frame.normal),
        base_origin=vec3(geometry.base_origin),
        offset_direction=vec3(geometry.offset_direction),
        rotational=geometry.rotational,
    )


def _section(ctx: JobContext, spec: SketchSection) -> tuple[SectionGeometry, Section]:
    built = ctx.session.built(ctx)
    mesh = built.result.mesh
    if mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    outputs = built.result.outputs

    def construction(feature_id: str) -> Construction:
        output = outputs.get(feature_id)
        if output is None or output.construction is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature_id})
        return output.construction

    geometry = section_geometry(spec, construction)
    ctx.check_cancelled()
    return geometry, cut(mesh.vertices, mesh.faces, geometry, mesh.vertex_normals)


@dataclass(frozen=True)
class SectionParams:
    section: SketchSection


@dataclass(frozen=True)
class SectionResult:
    frame: SketchFrame
    polylines: list[F32Array]
    """Section polylines, (n, 2) each, in sketch coordinates."""
    closed: list[bool]
    folded: F32Array | None
    """Rotational sections: scan points of all angles, folded into the half-plane (n, 2)."""
    noise: float
    suggested_tolerance: float


@command("sketch.section", lane=True)
def sketch_section(ctx: JobContext, params: SectionParams) -> SectionResult:
    """Cut the scan with a sketch plane (or the half-plane of a rotational section)."""
    geometry, section = _section(ctx, params.section)
    noise = section_noise(section)
    folded = None
    if section.rotational and section.support is not None:
        stride = max(1, len(section.support) // MAX_FOLDED_DISPLAY)
        folded = section.support[::stride].astype(np.float32)
    return SectionResult(
        frame=_frame(geometry),
        polylines=[p.astype(np.float32) for p in [*section.loops, *section.chains]],
        closed=[True] * len(section.loops) + [False] * len(section.chains),
        folded=folded,
        noise=noise,
        suggested_tolerance=suggested_tolerance(noise),
    )


@dataclass(frozen=True)
class AutoFitParams:
    sketch: SketchParams
    refit: bool = False
    """Keep the entities and move them onto the section instead of fitting anew."""


@dataclass(frozen=True)
class AutoFitResult:
    sketch: SketchParams
    fits: list[EntityFitInfo]
    profile: ProfileState
    frame: SketchFrame
    noise: float
    tolerance: float


def _fit_info(fit: EntityFit) -> EntityFitInfo:
    return EntityFitInfo(fit.entity, fit.points, fit.max_distance, fit.rms, fit.share, fit.passed)


def _result(fitted: FitResult, geometry: SectionGeometry) -> AutoFitResult:
    profile = fitted.profile
    return AutoFitResult(
        sketch=fitted.params,
        fits=[_fit_info(f) for f in fitted.fits],
        profile=ProfileState(
            closed=profile.closed,
            loops=[loop.id for loop in profile.loops],
            open_entities=profile.open_entities,
            gaps=[(float(g[0]), float(g[1])) for g in profile.gaps],
            branch_points=profile.branch_points,
        ),
        frame=_frame(geometry),
        noise=fitted.noise,
        tolerance=fitted.tolerance,
    )


@command("sketch.autoFit", lane=True)
def sketch_auto_fit(ctx: JobContext, params: AutoFitParams) -> AutoFitResult:
    """Fit lines, arcs and circles with constraints and snapped values to the section.

    With `refit`, the given sketch keeps its entities, constraints, snaps and typed
    dimensions; only the fitted entities move onto the current section.
    """
    geometry, section = _section(ctx, params.sketch.section)
    units = ctx.session.document.settings.snap_units
    fitted = auto_fit(params.sketch, section, units, params.refit)
    return _result(fitted, geometry)


@dataclass(frozen=True)
class FitEntityParams:
    sketch: SketchParams
    points: F64Array
    """Painted section points, (n, 2) in sketch coordinates, in painting order."""
    kind: Literal["auto", "line", "arc"] = "auto"


@dataclass(frozen=True)
class FitEntityResult:
    sketch: SketchParams
    entity: str
    max_distance: float
    tolerance: float


@command("sketch.fitEntity", lane=True)
def sketch_fit_entity(ctx: JobContext, params: FitEntityParams) -> FitEntityResult:
    """Add one line or arc through painted section points (type forced or automatic)."""
    _, section = _section(ctx, params.sketch.section)
    points = np.asarray(params.points, dtype=np.float64).reshape(-1, 2)
    sketch, entity, max_distance = fit_entity(params.sketch, section, points, params.kind)
    _, tolerance = fit_tolerance(params.sketch, section)
    return FitEntityResult(
        sketch=sketch, entity=entity, max_distance=max_distance, tolerance=tolerance
    )
