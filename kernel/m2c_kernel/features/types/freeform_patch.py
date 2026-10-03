"""Freeform patch: a B-spline surface fitted to scan triangles (height field).

The patch is construction geometry: `Construction.surface` holds its face over the
full parameter rectangle (slightly larger than the triangles by `margin`), which
`trim` uses to split bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

import numpy as np

from m2c_kernel.codes.freeform import ErrorCode, IssueCode, ProgressStage
from m2c_kernel.document.results import Construction, DisplaySource, FeatureOutput, Issue
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.freeform.api import PASS_SHARE, PatchResult, fit_scan_patch
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, Range, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore

type SpanCount = Annotated[int, Range(2, 64)]


@dataclass(frozen=True, kw_only=True)
class FreeformPatchParams:
    faces: BlobRef
    source_region: str | None = None
    spans: tuple[SpanCount, SpanCount] | None = None
    """B-spline spans (u, v); None chooses them from the patch size and the RMS."""
    smoothing: Annotated[float, Range(0.0, 1.0)] = 1e-4
    margin: Annotated[float, Range(0.0, 50.0)] = 2.0
    """How far the surface extends beyond the triangles, in mm."""


@dataclass(frozen=True, kw_only=True)
class FreeformPatchInput:
    faces: U32Array
    source_region: str | None = None
    spans: tuple[SpanCount, SpanCount] | None = None
    smoothing: Annotated[float, Range(0.0, 1.0)] = 1e-4
    margin: Annotated[float, Range(0.0, 50.0)] = 2.0


def _store(value: FreeformPatchInput, blobs: BlobStore) -> FreeformPatchParams:
    return FreeformPatchParams(
        faces=blobs.put(np.unique(value.faces).astype(np.uint32)),
        source_region=value.source_region,
        spans=value.spans,
        smoothing=value.smoothing,
        margin=value.margin,
    )


def patch_stats(result: PatchResult) -> dict[str, float | None]:
    """Feature statistics; keys are i18n keys of the feature's properties."""
    return {
        "freeform.stats.noise": result.noise,
        "freeform.stats.rms": result.fit.rms,
        "freeform.stats.max": result.fit.max_abs,
        "freeform.stats.withinTolerance": result.within_tolerance,
        "freeform.stats.faces": float(result.face_count),
        "freeform.stats.spansU": float(result.fit.surface.spans[0]),
        "freeform.stats.spansV": float(result.fit.surface.spans[1]),
        "freeform.stats.normalSpreadDeg": result.fit.normal_spread_deg,
    }


def patch_issues(result: PatchResult, tolerance: float) -> tuple[Issue, ...]:
    if result.within_tolerance >= PASS_SHARE:
        return ()
    share = round(result.within_tolerance, 4)
    return (Issue(IssueCode.POOR_FIT, {"share": share, "tolerance": tolerance}),)


def patch_display(result: PatchResult) -> tuple[DisplaySource, ...]:
    return (
        DisplaySource(
            kind="mesh", style="patch", positions=result.mesh_vertices, indices=result.mesh_faces
        ),
        DisplaySource(kind="lines", style="patch", positions=result.iso_lines),
    )


@feature_type(
    "freeformPatch",
    params=FreeformPatchParams,
    input=FreeformPatchInput,
    store=_store,
    reads=ReadSet(mesh=True, settings=("tolerance", "noise_override")),
)
class FreeformPatch:
    @staticmethod
    def references(params: FreeformPatchParams) -> Refs:
        return Refs()

    @staticmethod
    def evaluate(ctx: EvalContext, params: FreeformPatchParams) -> FeatureOutput:
        ctx.job.progress(None, ProgressStage.FITTING_PATCH)
        tolerance = ctx.settings.tolerance
        result = fit_scan_patch(
            ctx.mesh,
            ctx.face_set(params.faces),
            spans=params.spans,
            smoothing=params.smoothing,
            margin=params.margin,
            tolerance=tolerance,
            noise=ctx.settings.noise_override,
        )
        if result.face is None:
            raise KernelError(ErrorCode.INVALID_SURFACE)
        return FeatureOutput(
            construction=Construction(surface=result.face),
            display=patch_display(result),
            stats=patch_stats(result),
            issues=patch_issues(result, tolerance),
        )
