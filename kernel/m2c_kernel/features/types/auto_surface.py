"""Auto surface: a network of B-spline patches fitted to the scan or to selected triangles.

A closed scan gives a solid body whose faces are tagged `<id>:patch:<i>` (patch i of
the control cage). An open scan or selection gives an open shell, which is kept as
construction geometry (`Construction.surface`) with the issue `surfacing.openSurface`,
because bodies must be solids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from m2c_kernel.cad.occ_compat import TopAbs_FACE, indexed_map
from m2c_kernel.codes.surfacing import IssueCode
from m2c_kernel.document.results import (
    Body,
    BodyUpdate,
    Construction,
    DisplaySource,
    FeatureOutput,
    Issue,
)
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.protocol.wire import BlobRef, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore
    from m2c_kernel.surfacing.api import SurfaceModel

type SurfaceDetail = Literal["coarse", "medium", "fine"]
"""Cage size: about 1200, 3000 or 7500 patches."""
type SurfaceSmoothing = Literal["low", "medium", "high"]


@dataclass(frozen=True, kw_only=True)
class AutoSurfaceParams:
    faces: BlobRef | None = None
    """Scan triangles to surface; None surfaces the whole scan."""
    source_region: str | None = None
    detail: SurfaceDetail = "medium"
    smoothing: SurfaceSmoothing = "low"


@dataclass(frozen=True, kw_only=True)
class AutoSurfaceInput:
    """Like `AutoSurfaceParams`, but selected triangles arrive as indices."""

    faces: U32Array | None = None
    source_region: str | None = None
    detail: SurfaceDetail = "medium"
    smoothing: SurfaceSmoothing = "low"


def _store(value: AutoSurfaceInput, blobs: BlobStore) -> AutoSurfaceParams:
    faces = None if value.faces is None else blobs.put(np.unique(value.faces).astype(np.uint32))
    return AutoSurfaceParams(
        faces=faces,
        source_region=value.source_region,
        detail=value.detail,
        smoothing=value.smoothing,
    )


def surface_stats(model: SurfaceModel) -> dict[str, float | None]:
    """Feature statistics, read by the renderer's auto-surface view."""
    deviation = model.deviation
    return {
        "patches": float(model.patch_count),
        "closed": 1.0 if model.closed else 0.0,
        "deviationRms": deviation.rms,
        "deviationMean": deviation.mean,
        "deviationP95": deviation.p95,
        "deviationMax": deviation.max,
    }


def face_tags(feature_id: str, model: SurfaceModel) -> tuple[str, ...]:
    """One tag per B-Rep face in `TopExp` order, naming the patch it came from."""
    faces = indexed_map(model.shape, TopAbs_FACE)
    tags = [""] * faces.Extent()
    for patch, face in enumerate(model.faces):
        tags[faces.FindIndex(face) - 1] = f"{feature_id}:patch:{patch}"
    return tuple(tags)


def _shell_display(model: SurfaceModel) -> tuple[DisplaySource, ...]:
    from m2c_kernel.cad.tessellate import tessellate

    mesh = tessellate(model.shape)
    return (
        DisplaySource(kind="mesh", style="patch", positions=mesh.vertices, indices=mesh.triangles),
        DisplaySource(kind="lines", style="constructionEdges", positions=mesh.edge_segments),
    )


@feature_type(
    "autoSurface",
    params=AutoSurfaceParams,
    input=AutoSurfaceInput,
    store=_store,
    reads=ReadSet(mesh=True),
)
class AutoSurface:
    @staticmethod
    def references(params: AutoSurfaceParams) -> Refs:
        return Refs()

    @staticmethod
    def evaluate(ctx: EvalContext, params: AutoSurfaceParams) -> FeatureOutput:
        from m2c_kernel.surfacing.api import SurfacingOptions, auto_surface

        mesh = ctx.mesh
        faces = mesh.faces if params.faces is None else mesh.faces[ctx.face_set(params.faces)]
        synthetic = (
            mesh.synthetic if params.faces is None else mesh.synthetic[ctx.face_set(params.faces)]
        )
        model = auto_surface(
            mesh.vertices,
            faces,
            SurfacingOptions.from_levels(params.detail, params.smoothing),
            ctx.job,
            synthetic=synthetic,
        )
        issues: list[Issue] = []
        if model.ignored_parts:
            issues.append(Issue(IssueCode.PARTS_IGNORED, {"count": model.ignored_parts}))
        if not model.closed:
            issues.append(Issue(IssueCode.OPEN_SURFACE))
            return FeatureOutput(
                construction=Construction(surface=model.shape),
                display=_shell_display(model),
                stats=surface_stats(model),
                issues=tuple(issues),
            )
        body = Body(shape=model.shape, face_tags=face_tags(ctx.feature_id, model))
        return FeatureOutput(
            bodies=BodyUpdate(changed={ctx.feature_id: body}),
            stats=surface_stats(model),
            issues=tuple(issues),
        )
