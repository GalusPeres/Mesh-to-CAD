"""Freeform nets: generate, fit, the dense limit map for the renderer, and stored nets.

The freeform-net tool keeps the net (control points and quads) as its draft in the
renderer. These methods do the heavy work on it without committing; committing goes
through `doc.apply` with a `freeformNet` feature.

- `net.generate` makes a clean field-aligned net on the scan or on selected triangles
  and fits it (an exclusive job with progress: remeshing a large scan takes seconds).
- `net.fit` snaps a net to the scan (all control points, or with some held in place).
- `net.limitMap` returns the sparse map from control points to a dense mesh on the
  limit surface. It depends only on the quads, so the renderer asks again only after
  a topology change and redraws the surface itself while points are dragged.
- `net.featureNet` returns the stored net of a feature for editing.
- `net.pushPast` pushes the net's open border past planes and bodies, so that trimming
  against them cuts cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Annotated

import numpy as np

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.surfacing import ErrorCode, ProgressStage
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.document.results import Construction
from m2c_kernel.features.types.freeform_net import FreeformNetParams, net_arrays
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.mesh.child import ChildCallError
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, F64Array, Range, U8Array, U32Array
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.surfacing.cage import compact
from m2c_kernel.surfacing.net import (
    DEFAULT_ITERATIONS,
    DEFAULT_SMOOTHING,
    NetError,
    fit_net,
    generate_net,
    limit_map,
)
from m2c_kernel.surfacing.quadmesh import MAX_QUADS, MIN_QUADS, QuadMeshError

FREEFORM_NET = "freeformNet"
MAX_NET_VERTICES = 60_000

type SubdivisionLevel = Annotated[int, Range(1, 4)]


@dataclass(frozen=True)
class NetData:
    vertices: F64Array
    """(n, 3) control points in part coordinates."""
    quads: U32Array
    """(q, 4) control-point indices, counter-clockwise seen from outside."""


@dataclass(frozen=True, kw_only=True)
class GenerateParams:
    faces: U32Array | None = None
    """Scan triangles to cover; None covers the whole scan."""
    target_quads: Annotated[int, Range(MIN_QUADS, MAX_QUADS)] = 1500
    crease_deg: Annotated[float, Range(0.0, 90.0)] = 0.0
    """Sharp scan edges above this dihedral angle guide the net; 0 ignores them."""
    smoothing: Annotated[float, Range(0.0, 1.0)] = DEFAULT_SMOOTHING


@command("net.generate", lane=True, exclusive=True)
def net_generate(ctx: JobContext, params: GenerateParams) -> NetData:
    """A clean quad net on the scan (or the selected triangles), fitted to it."""
    mesh = _scan(ctx)
    vertices, faces = _part(mesh, params.faces)
    normals = _normals(vertices, faces)
    ctx.progress(None, ProgressStage.NET)
    try:
        net = generate_net(
            vertices,
            faces,
            normals,
            params.target_quads,
            crease_deg=params.crease_deg,
            smoothing=params.smoothing,
            check_cancelled=ctx.check_cancelled,
            progress=lambda share: ctx.progress(share, ProgressStage.FITTING),
        )
    except (QuadMeshError, ChildCallError) as error:
        raise KernelError(ErrorCode.NET_FAILED, details=str(error)) from error
    return NetData(net.vertices, net.quads.astype(np.uint32))


@dataclass(frozen=True, kw_only=True)
class FitParams:
    vertices: F64Array
    quads: U32Array
    faces: U32Array | None = None
    """Scan triangles to fit to; None uses the whole scan."""
    fixed: U8Array | None = None
    """Per control point, 1 to keep it in place."""
    smoothing: Annotated[float, Range(0.0, 1.0)] = DEFAULT_SMOOTHING
    iterations: Annotated[int, Range(1, 20)] = DEFAULT_ITERATIONS


@dataclass(frozen=True)
class FitResult:
    vertices: F64Array


@command("net.fit", lane=True)
def net_fit(ctx: JobContext, params: FitParams) -> FitResult:
    """Snap the net to the scan; fixed control points stay where they are."""
    cage, quads = _net(params.vertices, params.quads)
    fixed = None
    if params.fixed is not None:
        if len(params.fixed) != len(cage):
            raise KernelError(ErrorCode.NET_INVALID, details="fixed mask has the wrong length")
        fixed = np.asarray(params.fixed, dtype=bool)
    mesh = _scan(ctx)
    vertices, faces = _part(mesh, params.faces)
    ctx.progress(0.0, ProgressStage.FITTING)
    try:
        fitted = fit_net(
            cage,
            quads,
            vertices,
            _normals(vertices, faces),
            fixed=fixed,
            smoothing=params.smoothing,
            iterations=params.iterations,
            check_cancelled=ctx.check_cancelled,
            progress=lambda share: ctx.progress(share, ProgressStage.FITTING),
        )
    except NetError as error:
        raise KernelError(ErrorCode.NET_INVALID, details=str(error)) from error
    return FitResult(fitted)


@dataclass(frozen=True, kw_only=True)
class LimitMapParams:
    quads: U32Array
    vertex_count: Annotated[int, Range(4, MAX_NET_VERTICES)]
    level: SubdivisionLevel | None = None
    """Subdivision level of the dense mesh; None chooses 3 for small nets, else 2."""


@dataclass(frozen=True)
class LimitMapResult:
    """The dense limit-surface mesh as a CSR matrix over the control points.

    Row i gives fine vertex i as `sum(weights[k] * control[columns[k]])` for k in
    `rows[i] .. rows[i + 1]`; fine vertex i < vertexCount of the net is the limit
    position of control point i.
    """

    rows: U32Array
    columns: U32Array
    weights: F32Array
    triangles: U32Array
    """(t, 3) fine-vertex triangles, oriented like the net."""
    segments: U32Array
    """(s, 2) fine-vertex pairs along the net's edges."""
    segment_edges: U32Array
    """(s,) net edge of every segment (index into `edges`)."""
    edges: U32Array
    """(e, 2) control-point pairs of the net's edges."""
    boundary_edges: U8Array
    """(e,) 1 for edges on the net's open border."""
    border: U8Array
    """(fine vertices,) 1 on the net's open border."""
    face_edges: U8Array
    """(e,) 1 for edges between two CAD faces of the exported shape (patch layout)."""
    face_count: int
    """Number of CAD faces the net becomes."""
    level: int
    fine_count: int


@command("net.limitMap", lane=True)
def net_limit_map(ctx: JobContext, params: LimitMapParams) -> LimitMapResult:
    """The dense limit-surface mesh of a net's quads as a sparse map of its control points."""
    quads = np.asarray(params.quads, dtype=np.int64).reshape(-1, 4)
    try:
        result = limit_map(quads, params.vertex_count, params.level)
    except NetError as error:
        raise KernelError(ErrorCode.NET_INVALID, details=str(error)) from error
    matrix = result.matrix.tocsr()
    matrix.sort_indices()
    return LimitMapResult(
        rows=matrix.indptr.astype(np.uint32),
        columns=matrix.indices.astype(np.uint32),
        weights=matrix.data.astype(np.float32),
        triangles=result.triangles.astype(np.uint32),
        segments=result.segments.astype(np.uint32),
        segment_edges=result.segment_edges.astype(np.uint32),
        edges=result.edges.astype(np.uint32),
        boundary_edges=result.boundary_edges.astype(np.uint8),
        border=result.border.astype(np.uint8),
        face_edges=result.face_edges.astype(np.uint8),
        face_count=result.face_count,
        level=result.level,
        fine_count=int(matrix.shape[0]),
    )


@dataclass(frozen=True)
class FeatureNetParams:
    feature_id: str


@dataclass(frozen=True)
class FeatureNetResult:
    vertices: F64Array
    quads: U32Array
    faces: U32Array | None
    """The stored scan triangles; None when the net covers the whole scan."""
    scan_key: str


@command("net.featureNet")
def net_feature_net(ctx: JobContext, params: FeatureNetParams) -> FeatureNetResult:
    """The stored net of a `freeformNet` feature, for editing it."""
    document = ctx.session.document
    feature = document.feature(params.feature_id)
    if feature is None or document.scan is None:
        raise KernelError(DocumentError.UNKNOWN_FEATURE, {"feature": params.feature_id})
    if feature.type != FREEFORM_NET:
        raise KernelError(ErrorCode.NOT_FREEFORM_NET)
    params_json = feature.params if isinstance(feature.params, dict) else {}
    stored_faces = params_json.get("faces")
    stored = FreeformNetParams(
        vertices=str(params_json.get("vertices")),
        quads=str(params_json.get("quads")),
        faces=stored_faces if isinstance(stored_faces, str) else None,
    )
    vertices, quads = net_arrays(ctx.session.blobs, stored)
    faces = (
        None
        if stored.faces is None
        else ctx.session.blobs.get(stored.faces).astype(np.uint32, copy=False)
    )
    return FeatureNetResult(vertices, quads.astype(np.uint32), faces, document.scan.key)


@dataclass(frozen=True, kw_only=True)
class PushPastParams:
    vertices: F64Array
    quads: U32Array
    planes: list[str]
    """Plane features or origin planes."""
    bodies: list[str]
    tolerance: Annotated[float, Range(0.01, 5.0)] = 0.5
    """How far past the faces the border goes (mm)."""
    reach: Annotated[float, Range(0.1, 50.0)] = 2.0
    """Border points farther than this from every face stay (mm)."""
    fixed: U8Array | None = None
    """Per control point, 1 for pinned points (their limit points stay)."""


@dataclass(frozen=True)
class PushPastResult:
    vertices: F64Array
    moved: int
    """Border points that were pushed."""
    references: list[str]
    """Planes and bodies that pushed at least one point."""


@command("net.pushPast", lane=True)
def net_push_past(ctx: JobContext, params: PushPastParams) -> PushPastResult:
    """Push the net's open border past the given planes and bodies by `tolerance`."""
    from m2c_kernel.cad.distance import signed_distance
    from m2c_kernel.cad.references import reference_plane
    from m2c_kernel.surfacing.push import Reference, plane_reference, push_past
    from m2c_kernel.surfacing.subdivision import limit_matrix

    cage, quads = _net(params.vertices, params.quads)
    result = ctx.session.built(ctx).result
    limits = limit_matrix(quads, len(cage)) @ cage

    def construction(feature: str) -> Construction:
        output = result.outputs.get(feature)
        if output is None or output.construction is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature})
        return output.construction

    references = [
        plane_reference(plane, *reference_plane(plane, construction), limits)
        for plane in params.planes
    ]
    for body_id in params.bodies:
        body = result.bodies.get(body_id)
        if body is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": body_id})
        references.append(Reference(body_id, partial(signed_distance, body.shape)))
    fixed = None if params.fixed is None else np.asarray(params.fixed, dtype=bool)
    pushed = push_past(
        cage, quads, references, tolerance=params.tolerance, reach=params.reach, fixed=fixed
    )
    return PushPastResult(pushed.vertices, pushed.moved, list(pushed.references))


def _scan(ctx: JobContext) -> EvalMesh:
    mesh = ctx.session.built(ctx).result.mesh
    if mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    return mesh


def _part(mesh: EvalMesh, selected: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """Vertices and faces of the selected triangles (or the whole scan), compacted."""
    if selected is None:
        faces = mesh.faces
    else:
        indices = np.unique(np.asarray(selected, dtype=np.int64))
        indices = indices[(indices >= 0) & (indices < len(mesh.faces))]
        faces = mesh.faces[indices]
    if len(faces) < MIN_FIT_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(faces), "min": MIN_FIT_FACES})
    return compact(mesh.vertices, faces)


def _normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    from m2c_kernel.mesh.normals import vertex_normals

    normals: np.ndarray = vertex_normals(vertices, faces)
    return normals


def _net(vertices: np.ndarray, quads: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cage = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    net_quads = np.asarray(quads, dtype=np.int64).reshape(-1, 4)
    if len(cage) > MAX_NET_VERTICES or not np.all(np.isfinite(cage)):
        raise KernelError(ErrorCode.NET_INVALID, details="too many or non-finite control points")
    return cage, net_quads
