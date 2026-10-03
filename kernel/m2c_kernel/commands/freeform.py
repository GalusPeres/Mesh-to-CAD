"""Freeform patches and lofts: patch preview and the stored triangles of a feature.

Committing goes through `doc.apply` with a `freeformPatch` or `loft` feature. Lofts
are previewed with `doc.preview` like the other solid features.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated

import numpy as np

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.document.display import SceneItem, register_sources
from m2c_kernel.document.results import Construction
from m2c_kernel.features.common import StandardAxis
from m2c_kernel.features.types.freeform_patch import SpanCount, patch_display
from m2c_kernel.features.types.loft import loft_axis
from m2c_kernel.freeform.api import PASS_SHARE, body_range, fit_scan_patch, scan_extent
from m2c_kernel.geometry import Vec3, vec3
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import Range, U8Array, U32Array
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True, kw_only=True)
class FreeformPreviewParams:
    faces: U32Array
    spans: tuple[SpanCount, SpanCount] | None = None
    smoothing: Annotated[float, Range(0.0, 1.0)] = 1e-4
    margin: Annotated[float, Range(0.0, 50.0)] = 2.0


@dataclass(frozen=True)
class FreeformPreviewResult:
    spans: tuple[int, int]
    """Span count used (the automatic choice when none was given)."""
    noise: float
    rms: float
    max_abs: float
    within_tolerance: float
    passed: bool
    face_count: int
    normal_spread_deg: float
    face_states: U8Array
    """One `FACE_STATE` value per requested face, in request order."""
    items: tuple[SceneItem, ...]


PREVIEW_OWNER = "freeform-patch"


@command("freeform.preview", lane=True)
def freeform_preview(ctx: JobContext, params: FreeformPreviewParams) -> FreeformPreviewResult:
    """Fit a patch to the given triangles without committing: quality, pass/fail, display."""
    session = ctx.session
    built = session.built(ctx)
    mesh = built.result.mesh
    if mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    tolerance = built.document.settings.tolerance
    requested = np.asarray(params.faces, dtype=np.int64)
    result = fit_scan_patch(
        mesh,
        requested,
        spans=params.spans,
        smoothing=params.smoothing,
        margin=params.margin,
        tolerance=tolerance,
        noise=built.document.settings.noise_override,
    )
    per_face = np.zeros(len(mesh.faces), dtype=np.uint8)
    per_face[result.used_faces] = result.face_states
    valid = (requested >= 0) & (requested < len(mesh.faces))
    states = np.where(valid, per_face[np.where(valid, requested, 0)], 0).astype(np.uint8)
    key = _preview_key(mesh.key, params)
    items = register_sources(PREVIEW_OWNER, key, patch_display(result), session.scene)
    return FreeformPreviewResult(
        spans=result.fit.surface.spans,
        noise=result.noise,
        rms=result.fit.rms,
        max_abs=result.fit.max_abs,
        within_tolerance=result.within_tolerance,
        passed=result.within_tolerance >= PASS_SHARE,
        face_count=result.face_count,
        normal_spread_deg=result.fit.normal_spread_deg,
        face_states=states,
        items=tuple(items),
    )


def _preview_key(mesh_key: str, params: FreeformPreviewParams) -> str:
    digest = hashlib.sha256(mesh_key.encode("utf-8"))
    digest.update(np.ascontiguousarray(params.faces, dtype=np.uint32).tobytes())
    digest.update(json.dumps([params.spans, params.smoothing, params.margin]).encode("utf-8"))
    return f"freeform:{digest.hexdigest()[:24]}"


@dataclass(frozen=True, kw_only=True)
class FeatureFacesParams:
    feature_id: str


@dataclass(frozen=True)
class FeatureFacesResult:
    faces: U32Array | None
    """The stored triangles; None for a loft over the whole scan."""
    scan_key: str


@command("freeform.featureFaces")
def freeform_feature_faces(ctx: JobContext, params: FeatureFacesParams) -> FeatureFacesResult:
    """The stored triangles of a freeform patch or loft, for editing it with the selection."""
    document = ctx.session.document
    feature = document.feature(params.feature_id)
    if feature is None or document.scan is None:
        raise KernelError(DocumentError.UNKNOWN_FEATURE, {"feature": params.feature_id})
    if feature.type not in ("freeformPatch", "loft") or not isinstance(feature.params, dict):
        raise KernelError(ErrorCode.NOT_A_FREEFORM_FEATURE, {"feature": params.feature_id})
    faces = feature.params.get("faces")
    stored = ctx.session.blobs.get(faces).astype(np.uint32) if isinstance(faces, str) else None
    return FeatureFacesResult(faces=stored, scan_key=document.scan.key)


@dataclass(frozen=True, kw_only=True)
class LoftAxisParams:
    path: StandardAxis | str
    faces: U32Array | None = None


@dataclass(frozen=True)
class LoftAxisResult:
    point: Vec3
    direction: Vec3
    low: float
    high: float
    """Extent of the scan (or of `faces`) along the axis, in mm from `point`."""
    start: float
    end: float
    """Where the sections form one body to loft through (`body_range`): the default range."""


@command("freeform.loftAxis")
def freeform_loft_axis(ctx: JobContext, params: LoftAxisParams) -> LoftAxisResult:
    """The loft axis in part coordinates and the scan along it.

    `low` and `high` are how far the scan reaches; `start` and `end` where a loft fits.
    """
    built = ctx.session.built(ctx)
    mesh = built.result.mesh
    if mesh is None:
        raise KernelError(DocumentError.NO_SCAN)

    def construction(feature_id: str) -> Construction:
        output = built.result.outputs.get(feature_id)
        if output is None or output.construction is None:
            raise KernelError(ErrorCode.NOT_AN_AXIS, {"feature": feature_id})
        return output.construction

    axis = loft_axis(params.path, construction)
    faces = mesh.faces
    if params.faces is not None:
        chosen = np.asarray(params.faces, dtype=np.int64)
        chosen = chosen[(chosen >= 0) & (chosen < len(mesh.faces))]
        if len(chosen) == 0:
            raise KernelError(ErrorCode.NO_SECTION, {"position": 0.0})
        faces = mesh.faces[chosen]
    low, high = scan_extent(mesh.vertices[np.unique(faces)], axis)
    start, end = body_range(mesh.vertices, faces, axis, low, high)
    return LoftAxisResult(
        point=vec3(axis.point),
        direction=vec3(axis.direction),
        low=low,
        high=high,
        start=start,
        end=end,
    )
