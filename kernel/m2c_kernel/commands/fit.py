"""Primitive fitting.

`fit.preview` fits a triangle selection of the current scan with the same
pipeline as the fit feature and returns the primitive, statistics, type
alternatives, applied snaps, a pass/fail state per triangle and the scene items
of the construction preview. Committing goes through `doc.apply` with a `fit`
feature. `fit.featureFaces` returns the stored triangles of a fit feature, so
the fit tool can make them the working selection while the feature is edited.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.fit import ErrorCode
from m2c_kernel.document.display import SceneItem, register_sources
from m2c_kernel.document.model import DocumentSettings
from m2c_kernel.document.results import Construction
from m2c_kernel.features.types.fit import (
    FitFixed,
    FitRelation,
    build_constraints,
    fit_display,
    fit_request,
    relation_target,
)
from m2c_kernel.fitting.api import (
    AppliedSnap,
    FitAlternative,
    FitStats,
    Primitive,
    PrimitiveKind,
    SnapId,
    run_fit,
)
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import U8Array, U32Array, to_json
from m2c_kernel.session.jobs import JobContext, seeded_rng

PREVIEW_OWNER = "fit-primitive"


@dataclass(frozen=True, kw_only=True)
class PreviewParams:
    faces: U32Array
    scan_key: str
    kind: PrimitiveKind | Literal["auto"] = "auto"
    robust: bool = False
    fixed: FitFixed = field(default_factory=FitFixed)
    relation: FitRelation | None = None
    snap: bool = True
    rejected_snaps: list[SnapId] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PreviewResult:
    primitive: Primitive
    stats: FitStats
    alternatives: list[FitAlternative]
    snaps: list[AppliedSnap]
    face_states: U8Array
    """One `FACE_STATE` value per requested face, in request order."""
    used: U8Array
    """1 for each requested face the fit used (not synthetic, not a robust outlier)."""
    items: list[SceneItem]
    """Display items of the construction preview (`viewport.setPreviewItems`)."""


@command("fit.preview", lane=True)
def fit_preview(ctx: JobContext, params: PreviewParams) -> PreviewResult:
    """Fit the selected triangles without changing the document."""
    session = ctx.session
    built = session.built(ctx)
    document = built.document
    mesh = built.result.mesh
    if document.scan is None or mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    if params.scan_key != document.scan.key:
        raise KernelError(ErrorCode.STALE_SELECTION, {"scanKey": params.scan_key})

    def construction_of(feature_id: str) -> Construction:
        output = built.result.outputs.get(feature_id)
        if output is None or output.construction is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature_id})
        return output.construction

    target = relation_target(params.relation, construction_of)
    constraints = build_constraints(params.kind, params.fixed, params.relation, target)
    request = fit_request(
        params.kind,
        params.robust,
        constraints,
        params.snap,
        params.rejected_snaps,
        document.settings,
    )
    key = _request_key(params, mesh.key, document.settings)
    outcome = run_fit(mesh, params.faces, request, seeded_rng(key), ctx.check_cancelled)
    items = register_sources(PREVIEW_OWNER, key, fit_display(outcome), session.scene)
    return PreviewResult(
        primitive=outcome.primitive,
        stats=outcome.stats,
        alternatives=outcome.alternatives,
        snaps=outcome.snaps,
        face_states=outcome.face_states,
        used=np.isin(params.faces, outcome.used_faces).astype(np.uint8),
        items=items,
    )


def _request_key(params: PreviewParams, mesh_key: str, settings: DocumentSettings) -> str:
    """Identifies a preview: equal requests give equal random seeds and display keys."""
    digest = hashlib.sha256(mesh_key.encode("utf-8"))
    digest.update(np.ascontiguousarray(params.faces, dtype=np.uint32).tobytes())
    options = {
        "kind": params.kind,
        "robust": params.robust,
        "fixed": to_json(params.fixed, FitFixed),
        "relation": to_json(params.relation, FitRelation | None),
        "snap": params.snap,
        "rejected": sorted(params.rejected_snaps),
        "settings": to_json(settings, DocumentSettings),
    }
    digest.update(json.dumps(options, sort_keys=True).encode("utf-8"))
    return f"fitpreview:{digest.hexdigest()[:32]}"


@dataclass(frozen=True, kw_only=True)
class FeatureFacesParams:
    feature_id: str


@dataclass(frozen=True, kw_only=True)
class FeatureFacesResult:
    faces: U32Array
    scan_key: str


@command("fit.featureFaces")
def fit_feature_faces(ctx: JobContext, params: FeatureFacesParams) -> FeatureFacesResult:
    """The stored triangles of a fit feature, for editing it with the working selection."""
    document = ctx.session.document
    feature = document.feature(params.feature_id)
    if feature is None:
        raise KernelError(DocumentError.UNKNOWN_FEATURE, {"feature": params.feature_id})
    faces = feature.params.get("faces") if isinstance(feature.params, dict) else None
    if feature.type != "fit" or not isinstance(faces, str) or document.scan is None:
        raise KernelError(ErrorCode.NOT_A_FIT, {"feature": params.feature_id})
    stored = ctx.session.blobs.get(faces)
    return FeatureFacesResult(faces=stored.astype(np.uint32), scan_key=document.scan.key)
