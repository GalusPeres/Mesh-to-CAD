"""Mesh import and preparation.

Import has two phases so that the file path stays in the main process while
the renderer asks for the unit: `mesh.import` (main process only) loads the
file into a pending import and returns a report; `mesh.commitImport` or
`mesh.discardImport` follows from the import panel.

Every preparation command works on the current scan and, unless `dry_run` is
set, commits a new scan with a new key. Face sets in feature parameters and the
region labels are carried over through the exact face map of the operation.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated

import numpy as np

from m2c_kernel.codes.mesh import ErrorCode, ProgressStage
from m2c_kernel.document.model import (
    Document,
    DocumentSettings,
    Feature,
    LengthUnit,
    Scan,
    ScanOperation,
    ScanSource,
)
from m2c_kernel.geometry import Vec3, vec3
from m2c_kernel.limits import DEFAULT_TOLERANCE_MM, MAX_WORKING_FACES
from m2c_kernel.mesh.decimate import DecimationError, decimate
from m2c_kernel.mesh.load import PendingImport, RawMesh, read_mesh, weld_vertices
from m2c_kernel.mesh.remap import remap_face_set, remap_labels
from m2c_kernel.mesh.repair import (
    REPAIR_STEPS,
    MeshChange,
    RepairStep,
    boundary_loops,
    component_labels,
    delete_faces,
    fill_holes,
    remove_small_parts,
    repair,
    signed_volume,
)
from m2c_kernel.mesh.topology import edge_topology, pack_rows
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import JsonValue, Range, U32Array
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext

UNIT_SCALE: dict[LengthUnit, float] = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
_TOLERANCE_STEPS_MM = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
DEFAULT_MIN_PART_RATIO = 0.01
DEFAULT_MIN_PART_FACES = 100
MAX_SMOOTHING_ITERATIONS = 20


# --------------------------------------------------------------------------- import


@dataclass(frozen=True)
class ImportParams:
    path: str


@dataclass(frozen=True)
class ImportReport:
    """What the import panel shows before the user confirms the unit.

    Bounds and `noise` are in file units. `suggested_unit` is a guess (a part
    smaller than two units is almost certainly in metres); the user always
    confirms. `proposed_tolerance` holds the tolerance each unit would give.
    """

    pending_id: str
    file_name: str
    face_count: int
    vertex_count: int
    merged_vertices: int
    bounds_min: Vec3
    bounds_max: Vec3
    suggested_unit: LengthUnit
    noise: float | None
    proposed_tolerance: dict[str, float]
    requires_reduction: bool


@command("mesh.import", caller="main")
def mesh_import(ctx: JobContext, params: ImportParams) -> ImportReport:
    """Load a mesh file into a pending import (called by the main process after a dialog)."""
    path = Path(params.path)
    ctx.progress(None, ProgressStage.READING)
    raw = read_mesh(path)
    ctx.check_cancelled()
    ctx.progress(None, ProgressStage.WELDING)
    welded, merged = weld_vertices(raw)
    del raw
    ctx.check_cancelled()
    ctx.progress(None, ProgressStage.ESTIMATING_NOISE)
    noise = _estimate_noise(welded)
    pending = PendingImport(
        id=uuid.uuid4().hex[:12],
        file_name=path.name,
        sha256=_file_sha256(path),
        mesh=welded,
        merged_vertices=merged,
    )
    ctx.session.pending_imports[pending.id] = pending
    low, high = welded.vertices.min(axis=0), welded.vertices.max(axis=0)
    diagonal = float(np.linalg.norm(high - low))
    return ImportReport(
        pending_id=pending.id,
        file_name=pending.file_name,
        face_count=len(welded.faces),
        vertex_count=len(welded.vertices),
        merged_vertices=merged,
        bounds_min=vec3(low),
        bounds_max=vec3(high),
        suggested_unit="m" if diagonal < 2.0 else "mm",
        noise=noise,
        proposed_tolerance={
            unit: propose_tolerance(None if noise is None else noise * scale)
            for unit, scale in UNIT_SCALE.items()
        },
        requires_reduction=len(welded.faces) > MAX_WORKING_FACES,
    )


@dataclass(frozen=True)
class CommitImportParams:
    pending_id: str
    unit: LengthUnit
    reduce_to: Annotated[int, Range(1_000, MAX_WORKING_FACES)] | None = None


@dataclass(frozen=True)
class CommitImportResult:
    revision: int
    counts: dict[str, int]


@command("mesh.commitImport", exclusive=True)
def mesh_commit_import(ctx: JobContext, params: CommitImportParams) -> CommitImportResult:
    """Scale, reduce if needed, repair and make the pending import the scan of a new document."""
    session = ctx.session
    pending = session.pending_imports.get(params.pending_id)
    if pending is None:
        raise KernelError(ErrorCode.UNKNOWN_IMPORT, {"pendingId": params.pending_id})
    mesh = pending.mesh
    target = params.reduce_to
    if target is None and len(mesh.faces) > MAX_WORKING_FACES:
        raise KernelError(
            ErrorCode.REDUCTION_REQUIRED, {"faces": len(mesh.faces), "maxFaces": MAX_WORKING_FACES}
        )

    scale = UNIT_SCALE[params.unit]
    low, high = mesh.vertices.min(axis=0) * scale, mesh.vertices.max(axis=0) * scale
    origin = (low + high) / 2.0
    working = RawMesh(mesh.vertices * scale - origin, mesh.faces)
    counts: dict[str, int] = {"mergedVertices": pending.merged_vertices}

    ctx.progress(0.2, ProgressStage.REPAIRING)
    prepared = default_preparation(working)
    ctx.check_cancelled()
    if target is not None and target < len(prepared.mesh.faces):
        ctx.progress(0.4, ProgressStage.DECIMATING)
        prepared = prepared.then(_decimate(ctx, prepared.mesh, target))
    counts |= prepared.counts

    ctx.progress(0.8, ProgressStage.ESTIMATING_NOISE)
    noise = _estimate_noise(prepared.mesh)
    ctx.check_cancelled()
    scan = _new_scan(
        session.blobs,
        prepared.mesh,
        np.zeros(len(prepared.mesh.faces), dtype=bool),
        source=ScanSource(
            file_name=pending.file_name, sha256=pending.sha256, import_unit=params.unit
        ),
        origin=origin,
        noise=noise,
        operations=(ScanOperation(op="import", counts=counts),),
    )
    document = replace(
        Document.empty(), scan=scan, settings=DocumentSettings(tolerance=propose_tolerance(noise))
    )
    snapshot = session.commit(document, "import", ctx)
    del session.pending_imports[pending.id]
    return CommitImportResult(revision=snapshot.revision, counts=counts)


def default_preparation(mesh: RawMesh) -> MeshChange:
    """Repair applied to every import: all repair steps plus removal of small parts."""
    repaired = repair(mesh)
    return repaired.then(
        remove_small_parts(repaired.mesh, DEFAULT_MIN_PART_RATIO, DEFAULT_MIN_PART_FACES)
    )


@dataclass(frozen=True)
class DiscardImportParams:
    pending_id: str


@dataclass(frozen=True)
class DiscardImportResult:
    pass


@command("mesh.discardImport")
def mesh_discard_import(ctx: JobContext, params: DiscardImportParams) -> DiscardImportResult:
    """Forget a pending import (the user cancelled the import panel)."""
    ctx.session.pending_imports.pop(params.pending_id, None)
    return DiscardImportResult()


# --------------------------------------------------------------------------- inspection


@dataclass(frozen=True)
class InspectParams:
    pass


@dataclass(frozen=True)
class MeshReport:
    """Mesh condition shown in the mesh info panel. Lengths in mm, areas in mm²."""

    scan_key: str
    face_count: int
    vertex_count: int
    watertight: bool
    boundary_loops: int
    non_manifold_edges: int
    inconsistent_edges: int
    components: int
    degenerate_faces: int
    duplicate_faces: int
    synthetic_faces: int
    area: float
    volume: float | None
    noise: float | None


@command("mesh.inspect")
def mesh_inspect(ctx: JobContext, params: InspectParams) -> MeshReport:
    """Condition of the current scan (holes, defects, components, area and volume)."""
    scan, mesh = _current_scan(ctx)
    ctx.progress(None, ProgressStage.INSPECTING)
    faces = mesh.faces
    topology = edge_topology(faces)
    loops = boundary_loops(mesh, topology)
    components, _ = component_labels(mesh)
    v = mesh.vertices
    cross = np.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    repeated = (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2])
    repeated |= faces[:, 0] == faces[:, 2]
    unique_faces = len(np.unique(pack_rows(np.sort(faces, axis=1))))
    watertight = bool((topology.valence == 2).all())
    synthetic = ctx.session.blobs.get(scan.synthetic) if scan.synthetic is not None else None
    return MeshReport(
        scan_key=scan.key,
        face_count=len(faces),
        vertex_count=len(v),
        watertight=watertight,
        boundary_loops=len(loops.loops) + loops.skipped,
        non_manifold_edges=topology.non_manifold_edge_count,
        inconsistent_edges=topology.inconsistent_edge_count(),
        components=components,
        degenerate_faces=int((repeated | (areas <= 0.0)).sum()),
        duplicate_faces=len(faces) - unique_faces,
        synthetic_faces=0 if synthetic is None else int(np.count_nonzero(synthetic)),
        area=float(areas.sum()),
        volume=abs(signed_volume(mesh)) if watertight else None,
        noise=scan.noise,
    )


# --------------------------------------------------------------------------- preparation


@dataclass(frozen=True)
class MeshEditResult:
    """Counts of a preparation step; `revision` is None for a dry run."""

    counts: dict[str, int]
    face_count: int
    vertex_count: int
    revision: int | None


@dataclass(frozen=True)
class RepairParams:
    steps: tuple[RepairStep, ...] = REPAIR_STEPS
    dry_run: bool = False


@command("mesh.repair", lane=True)
def mesh_repair(ctx: JobContext, params: RepairParams) -> MeshEditResult:
    """Weld, remove degenerate and duplicate faces, fix winding and orientation."""
    return _edit(ctx, "repair", params.dry_run, lambda mesh: repair(mesh, params.steps))


@dataclass(frozen=True)
class RemoveSmallPartsParams:
    min_ratio: Annotated[float, Range(0.0, 1.0)] = DEFAULT_MIN_PART_RATIO
    min_faces: Annotated[int, Range(0, 1_000_000)] = DEFAULT_MIN_PART_FACES
    dry_run: bool = False


@command("mesh.removeSmallParts", lane=True)
def mesh_remove_small_parts(ctx: JobContext, params: RemoveSmallPartsParams) -> MeshEditResult:
    """Remove loose parts (debris) smaller than a share of the largest part."""
    return _edit(
        ctx,
        "removeSmallParts",
        params.dry_run,
        lambda mesh: remove_small_parts(mesh, params.min_ratio, params.min_faces),
    )


@dataclass(frozen=True)
class FillHolesParams:
    max_perimeter: Annotated[float, Range(0.0, 1e6)]
    dry_run: bool = False


@command("mesh.fillHoles", lane=True)
def mesh_fill_holes(ctx: JobContext, params: FillHolesParams) -> MeshEditResult:
    """Close holes up to a perimeter; new faces are marked synthetic and never fitted."""
    return _edit(
        ctx, "fillHoles", params.dry_run, lambda mesh: fill_holes(mesh, params.max_perimeter)
    )


@dataclass(frozen=True)
class DecimateParams:
    target_faces: Annotated[int, Range(1_000, MAX_WORKING_FACES)]
    dry_run: bool = False


@command("mesh.decimate", lane=True, exclusive=True)
def mesh_decimate(ctx: JobContext, params: DecimateParams) -> MeshEditResult:
    """Reduce the scan to a target triangle count.

    A dry run only reports the counts; reducing is too slow to preview.
    """
    if params.dry_run:
        _, mesh = _current_scan(ctx)
        after = min(params.target_faces, len(mesh.faces))
        counts = {"facesBefore": len(mesh.faces), "facesAfter": after}
        return MeshEditResult(counts, after, len(mesh.vertices), None)
    return _edit(ctx, "decimate", False, lambda mesh: _decimate(ctx, mesh, params.target_faces))


@dataclass(frozen=True)
class DeleteFacesParams:
    faces: U32Array
    scan_key: str


@command("mesh.deleteFaces")
def mesh_delete_faces(ctx: JobContext, params: DeleteFacesParams) -> MeshEditResult:
    """Delete selected faces; a selection made on an older scan is rejected."""
    scan, mesh = _current_scan(ctx)
    if params.scan_key != scan.key:
        raise KernelError(ErrorCode.STALE_SELECTION, {"scanKey": params.scan_key})
    faces = np.asarray(params.faces, dtype=np.int64)
    if len(faces) and (faces.max() >= len(mesh.faces)):
        raise KernelError(ErrorCode.STALE_SELECTION, {"scanKey": params.scan_key})
    return _edit(ctx, "deleteFaces", False, lambda current: delete_faces(current, faces))


@dataclass(frozen=True)
class SetSmoothingParams:
    iterations: Annotated[int, Range(0, MAX_SMOOTHING_ITERATIONS)]


@dataclass(frozen=True)
class SetSmoothingResult:
    revision: int


@command("mesh.setSmoothing")
def mesh_set_smoothing(ctx: JobContext, params: SetSmoothingParams) -> SetSmoothingResult:
    """Display smoothing of the scan (Taubin); fitting always uses the unsmoothed scan."""
    scan, _ = _current_scan(ctx)
    document = ctx.session.document
    smoothed = replace(scan, display_smoothing=params.iterations)
    snapshot = ctx.session.commit(replace(document, scan=smoothed), "smoothing", ctx)
    return SetSmoothingResult(revision=snapshot.revision)


# --------------------------------------------------------------------------- helpers


def propose_tolerance(noise: float | None) -> float:
    """Project tolerance proposed from the scan noise: the first step at or above 2.5 sigma."""
    if noise is None or not np.isfinite(noise):
        return DEFAULT_TOLERANCE_MM
    wanted = 2.5 * noise
    return next((step for step in _TOLERANCE_STEPS_MM if step >= wanted), _TOLERANCE_STEPS_MM[-1])


def _edit(
    ctx: JobContext, op: str, dry_run: bool, operation: Callable[[RawMesh], MeshChange]
) -> MeshEditResult:
    scan, mesh = _current_scan(ctx)
    change = operation(mesh)
    ctx.check_cancelled()
    if len(change.mesh.faces) == 0:
        raise KernelError(ErrorCode.NOTHING_LEFT)
    result_mesh = change.mesh
    if dry_run:
        return MeshEditResult(
            change.counts, len(result_mesh.faces), len(result_mesh.vertices), None
        )
    revision = _commit_change(ctx, scan, change, op)
    return MeshEditResult(
        change.counts, len(result_mesh.faces), len(result_mesh.vertices), revision
    )


def _current_scan(ctx: JobContext) -> tuple[Scan, RawMesh]:
    scan = ctx.session.document.scan
    if scan is None:
        raise KernelError(ErrorCode.NO_SCAN)
    blobs = ctx.session.blobs
    vertices = blobs.get(scan.vertices).astype(np.float64)
    faces = blobs.get(scan.faces).astype(np.int64)
    return scan, RawMesh(vertices, faces)


def _commit_change(ctx: JobContext, scan: Scan, change: MeshChange, op: str) -> int:
    session = ctx.session
    blobs = session.blobs
    old_faces = scan.face_count
    has_source = change.new_to_old >= 0
    source = np.where(has_source, change.new_to_old, 0)
    synthetic = change.synthetic.copy()
    if scan.synthetic is not None:
        old_synthetic = blobs.get(scan.synthetic).astype(bool)
        synthetic |= has_source & old_synthetic[source]
    new_scan = _new_scan(
        blobs,
        change.mesh,
        synthetic,
        source=scan.source,
        origin=np.asarray(scan.origin),
        noise=scan.noise,
        operations=(*scan.operations, ScanOperation(op=op, counts=change.counts)),
        display_smoothing=scan.display_smoothing,
    )
    document = session.document
    regions = document.regions
    if regions.labels is not None:
        labels = remap_labels(blobs.get(regions.labels).astype(np.uint16), change.new_to_old)
        sizes = np.bincount(
            labels, minlength=max((item.label for item in regions.items), default=0) + 1
        )
        items = tuple(replace(item, face_count=int(sizes[item.label])) for item in regions.items)
        regions = replace(regions, labels=blobs.put(labels), items=items)
    features = tuple(
        _remap_feature(feature, blobs, change, old_faces) for feature in document.features
    )
    document = replace(document, scan=new_scan, regions=regions, features=features)
    return session.commit(document, op, ctx).revision


def _remap_feature(feature: Feature, blobs: BlobStore, change: MeshChange, old: int) -> Feature:
    """Carry every face set (a 1-D integer blob) in the parameters over to the new scan."""

    def remap(value: JsonValue) -> JsonValue:
        if isinstance(value, str) and value.startswith("blob:"):
            array = blobs.get(value)
            if array.ndim == 1 and np.issubdtype(array.dtype, np.integer):
                faces = remap_face_set(array.astype(np.int64), change.new_to_old, old)
                return blobs.put(faces.astype(array.dtype))
            return value
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        return value

    return replace(feature, params=remap(feature.params))


def _new_scan(
    blobs: BlobStore,
    mesh: RawMesh,
    synthetic: np.ndarray,
    *,
    source: ScanSource,
    origin: np.ndarray,
    noise: float | None,
    operations: tuple[ScanOperation, ...],
    display_smoothing: int = 0,
) -> Scan:
    vertices_ref = blobs.put(mesh.vertices.astype(np.float32))
    faces_ref = blobs.put(mesh.faces.astype(np.uint32))
    synthetic_ref = blobs.put(synthetic.astype(np.uint8)) if synthetic.any() else None
    key = hashlib.sha256(f"{vertices_ref}|{faces_ref}|{synthetic_ref}".encode()).hexdigest()
    return Scan(
        key=f"scan:{key[:24]}",
        source=source,
        vertices=vertices_ref,
        faces=faces_ref,
        synthetic=synthetic_ref,
        vertex_count=len(mesh.vertices),
        face_count=len(mesh.faces),
        origin=vec3(origin),
        noise=noise,
        display_smoothing=display_smoothing,
        operations=operations,
    )


def _decimate(ctx: JobContext, mesh: RawMesh, target: int) -> MeshChange:
    ctx.progress(None, ProgressStage.DECIMATING)
    try:
        return decimate(mesh, target, ctx.check_cancelled)
    except DecimationError as error:
        raise KernelError(ErrorCode.DECIMATION_FAILED, details=str(error)) from error


def _estimate_noise(mesh: RawMesh) -> float | None:
    from m2c_kernel.mesh.normals import jet_fit, vertex_normals

    if len(mesh.vertices) < 100:
        return None
    jet = jet_fit(mesh.vertices, vertex_normals(mesh.vertices, mesh.faces))
    return jet.noise


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
