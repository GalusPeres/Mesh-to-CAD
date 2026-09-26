"""Deviation analysis and measurements (the Prüfen stage).

- `inspection.deviation` colours the scan: one signed distance per scan vertex
  (positive = excess material), NaN beyond the search distance. Exclusive: it runs
  alone and can take seconds on large scans.
- `inspection.previewDeviation` summarises how well the body of a tool preview fits
  the scan, on at most 50,000 nearby scan points (ARCHITECTURE.md 4.7).
- `inspection.measure` measures between fits, reference geometry, origin planes and
  axes, and body faces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np

from m2c_kernel.cad.occ_compat import TopAbs_FACE, TopoDS, indexed_map
from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.inspection import ErrorCode
from m2c_kernel.inspection.api import (
    BodyInput,
    DeviationStats,
    DistanceKind,
    FaceDeviation,
    GeometryKind,
    Item,
    OriginItem,
    deviation_map,
    deviation_summary,
    fit_covariance,
    geometry_of_construction,
    geometry_of_face,
    geometry_of_origin,
    measure_items,
)
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, Range
from m2c_kernel.session.jobs import JobContext, seeded_rng
from m2c_kernel.session.session import BuiltDocument

MAX_SEARCH_DISTANCE_MM = 50.0


def _bodies(built: BuiltDocument, ids: list[str]) -> list[BodyInput]:
    """The requested bodies of the current document (all when `ids` is empty)."""
    result = built.result
    wanted = ids or list(result.bodies)
    if not wanted:
        raise KernelError(ErrorCode.NO_BODY)
    missing = [body_id for body_id in wanted if body_id not in result.bodies]
    if missing:
        raise KernelError(ErrorCode.UNKNOWN_BODY, {"body": missing[0]})
    return [
        BodyInput(body_id, result.body_keys[body_id], result.bodies[body_id]) for body_id in wanted
    ]


# --------------------------------------------------------------------------- deviation map


@dataclass(frozen=True)
class DeviationParams:
    bodies: list[str]
    """Body ids; empty compares with every body."""
    max_distance: Annotated[float, Range(0.01, MAX_SEARCH_DISTANCE_MM)]


@dataclass(frozen=True)
class DeviationResult:
    """Deviation per scan vertex and per scan face; NaN means no data.

    The face values are the mean of each face's vertices (the value under the cursor).
    """

    revision: int
    scan_key: str
    bodies: list[str]
    max_distance: float
    values: F32Array
    face_values: F32Array
    stats: DeviationStats
    faces: list[FaceDeviation]


@command("inspection.deviation", lane=True, exclusive=True)
def inspection_deviation(ctx: JobContext, params: DeviationParams) -> DeviationResult:
    """Signed distance of every scan vertex to the nearest body surface, with statistics."""
    built = ctx.session.built(ctx)
    mesh = built.result.mesh
    if mesh is None or built.document.scan is None:
        raise KernelError(DocumentError.NO_SCAN)
    bodies = _bodies(built, params.bodies)
    tolerance = built.document.settings.tolerance
    result = deviation_map(
        mesh.vertices, mesh.faces, mesh.synthetic, bodies, tolerance, params.max_distance, ctx
    )
    return DeviationResult(
        revision=built.document.revision,
        scan_key=built.document.scan.key,
        bodies=[body.body_id for body in bodies],
        max_distance=params.max_distance,
        values=result.values,
        face_values=result.face_values,
        stats=result.stats,
        faces=result.faces,
    )


@dataclass(frozen=True)
class PreviewDeviationParams:
    result_key: str
    """Result key of the previewed feature (from `doc.preview`)."""


@dataclass(frozen=True)
class PreviewDeviationResult:
    bodies: list[str]
    stats: DeviationStats
    points: int
    """Scan points compared (near the body, at most 50,000)."""


@command("inspection.previewDeviation", lane=True)
def inspection_preview_deviation(
    ctx: JobContext, params: PreviewDeviationParams
) -> PreviewDeviationResult:
    """Deviation summary of the bodies a cached preview result creates or changes."""
    session = ctx.session
    cached = session.results.get(params.result_key)
    if cached is None:
        raise KernelError(ErrorCode.NO_PREVIEW)
    changed = cached.output.bodies.changed
    if not changed:
        raise KernelError(ErrorCode.NO_BODY)
    built = session.built(ctx)
    mesh = built.result.mesh
    if mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    bodies = [
        BodyInput(body_id, f"{params.result_key}:{body_id}", body)
        for body_id, body in changed.items()
    ]
    settings = built.document.settings
    stats, points = deviation_summary(
        mesh.vertices,
        bodies,
        settings.tolerance,
        settings.deviation_max_distance,
        seeded_rng(f"previewDeviation:{params.result_key}"),
        ctx,
    )
    return PreviewDeviationResult(bodies=list(changed), stats=stats, points=points)


# --------------------------------------------------------------------------- measure


@dataclass(frozen=True, kw_only=True)
class FeatureItem:
    """A fit or a reference geometry feature."""

    type: Literal["feature"] = "feature"
    feature: str


@dataclass(frozen=True, kw_only=True)
class BodyFaceItem:
    """B-Rep face `face` (index into the body's `faceTags`) of a body."""

    type: Literal["bodyFace"] = "bodyFace"
    body: str
    face: int


@dataclass(frozen=True, kw_only=True)
class OriginPartItem:
    """An origin plane (XY, YZ, XZ) or axis (X, Y, Z)."""

    type: Literal["origin"] = "origin"
    item: OriginItem


type MeasureItem = FeatureItem | BodyFaceItem | OriginPartItem


@dataclass(frozen=True)
class MeasureParams:
    a: MeasureItem
    b: MeasureItem | None = None


@dataclass(frozen=True)
class MeasuredValue:
    value: float
    uncertainty: float | None
    """Standard uncertainty from the fit (None for exact geometry)."""


@dataclass(frozen=True)
class MeasureResult:
    """Distance in mm (the distance kind says which), angle in degrees, diameters in mm."""

    kind_a: GeometryKind
    kind_b: GeometryKind | None
    distance: MeasuredValue | None
    distance_kind: DistanceKind | None
    angle_deg: MeasuredValue | None
    parallel: bool
    diameter_a: MeasuredValue | None
    diameter_b: MeasuredValue | None


@command("inspection.measure", lane=True)
def inspection_measure(ctx: JobContext, params: MeasureParams) -> MeasureResult:
    """Distance, angle and diameters between two items, or the diameter of one."""
    built = ctx.session.built(ctx)
    rng = seeded_rng(f"measure:{built.document.revision}:{_canonical(params)}")
    a = _item(ctx, built, params.a, rng)
    b = _item(ctx, built, params.b, rng) if params.b is not None else None
    result = measure_items(a, b, rng)

    def value(nominal: float | None, sigma: float | None) -> MeasuredValue | None:
        return None if nominal is None else MeasuredValue(nominal, sigma)

    return MeasureResult(
        kind_a=a.geometry.kind,
        kind_b=None if b is None else b.geometry.kind,
        distance=value(result.distance, result.distance_sigma),
        distance_kind=result.distance_kind,
        angle_deg=value(result.angle, result.angle_sigma),
        parallel=result.parallel,
        diameter_a=value(result.diameter_a, result.diameter_a_sigma),
        diameter_b=value(result.diameter_b, result.diameter_b_sigma),
    )


def _canonical(params: MeasureParams) -> str:
    def plain(item: MeasureItem | None) -> object:
        return None if item is None else vars(item)

    return json.dumps([plain(params.a), plain(params.b)], sort_keys=True)


def _item(
    ctx: JobContext, built: BuiltDocument, item: MeasureItem, rng: np.random.Generator
) -> Item:
    match item:
        case OriginPartItem(item=origin):
            return Item(geometry_of_origin(origin))
        case BodyFaceItem(body=body_id, face=face_index):
            body = built.result.bodies.get(body_id)
            if body is None:
                raise KernelError(ErrorCode.UNKNOWN_ITEM, {"body": body_id})
            faces = indexed_map(body.shape, TopAbs_FACE)
            if not 0 <= face_index < faces.Extent():
                raise KernelError(ErrorCode.UNKNOWN_ITEM, {"body": body_id, "face": face_index})
            return Item(geometry_of_face(TopoDS.Face(faces.FindKey(face_index + 1))))
        case FeatureItem(feature=feature_id):
            return _feature_item(ctx, built, feature_id, rng)


def _feature_item(
    ctx: JobContext, built: BuiltDocument, feature_id: str, rng: np.random.Generator
) -> Item:
    feature = built.document.feature(feature_id)
    if feature is None:
        raise KernelError(ErrorCode.UNKNOWN_ITEM, {"feature": feature_id})
    output = built.result.outputs.get(feature_id)
    status = built.result.statuses.get(feature_id)
    if output is None or status is None or status.state not in ("ok", "warning"):
        raise KernelError(ErrorCode.ITEM_UNAVAILABLE, {"feature": feature_id})
    construction = output.construction
    geometry = None if construction is None else geometry_of_construction(construction)
    if construction is None or geometry is None:
        raise KernelError(ErrorCode.NOT_MEASURABLE, {"feature": feature_id})
    covariance = None
    faces_ref = feature.params.get("faces") if isinstance(feature.params, dict) else None
    mesh = built.result.mesh
    if construction.primitive is not None and isinstance(faces_ref, str) and mesh is not None:
        # A fit: its uncertainty comes from the scan points it was fitted to.
        faces = ctx.session.blobs.get(faces_ref).astype(np.int64)
        points = mesh.vertices[np.unique(mesh.faces[faces].ravel())]
        covariance = fit_covariance(construction.primitive, points, rng)
    return Item(geometry, covariance)
