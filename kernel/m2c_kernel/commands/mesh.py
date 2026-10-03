"""Mesh import and preparation.

Import has two phases so that the file path stays in the main process while
the renderer asks for the unit: `mesh.import` (main process only) loads the
file into a pending import and returns a report; `mesh.commitImport` or
`mesh.discardImport` follows from the import panel.

Every preparation command works on the current scan. Unless `dry_run` is set or
nothing changes, it commits a new scan with a new key and carries the face sets
stored in features and the region labels over through the face map of the
operation (`m2c_kernel.mesh.remap`).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.mesh import ErrorCode, ProgressStage
from m2c_kernel.document.model import (
    Document,
    DocumentSettings,
    LengthUnit,
    Regions,
    Scan,
    ScanOperation,
    ScanSource,
)
from m2c_kernel.geometry import Vec3, vec3
from m2c_kernel.limits import DEFAULT_TOLERANCE_MM, MAX_WORKING_FACES
from m2c_kernel.mesh.decimate import DecimationError, decimate
from m2c_kernel.mesh.load import PendingImport, RawMesh, read_mesh, weld_vertices
from m2c_kernel.mesh.normals import (
    DEFAULT_CELL_MM,
    NoiseEstimate,
    estimate_noise,
    face_normals,
    vertex_normals,
)
from m2c_kernel.mesh.remap import remap_face_set, remap_labels
from m2c_kernel.mesh.repair import (
    DEFAULT_MIN_PART_FACES,
    DEFAULT_MIN_PART_RATIO,
    REPAIR_STEPS,
    MeshChange,
    RepairStep,
    boundary_loops,
    component_labels,
    delete_faces,
    fill_holes,
    parts_to_keep,
    remove_degenerate_faces,
    remove_duplicate_faces,
    remove_small_parts,
    repair,
    signed_volume,
)
from m2c_kernel.mesh.smoothing import MAX_ITERATIONS
from m2c_kernel.mesh.topology import edge_topology
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import BlobRef, JsonValue, Range, U32Array
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext, seeded_rng

UNIT_SCALE: dict[LengthUnit, float] = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
_TOLERANCE_STEPS_MM = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
_METRES_BELOW_DIAGONAL = 2.0
_FINE_SAMPLE_SHARE = 0.9
_NO_FACES = np.zeros(0, dtype=np.uint32)
_IMPORT_REPAIR_STEPS: tuple[RepairStep, ...] = (
    "degenerate",
    "duplicates",
    "winding",
    "orientation",
)


# --------------------------------------------------------------------------- import


@dataclass(frozen=True)
class ImportParams:
    path: str


@dataclass(frozen=True)
class ImportReport:
    """What the import panel shows before the user confirms the unit.

    Bounds are in file units. `noise` (mm) and `proposed_tolerance` (mm) are given
    per unit, because the noise is measured at the physical scale the unit implies.
    `suggested_unit` is a guess (a part smaller than two units is almost certainly
    stored in metres); the user always confirms. `counts` holds `mergedVertices`
    and `nonFiniteFaces` (dropped while reading).
    """

    pending_id: str
    file_name: str
    face_count: int
    vertex_count: int
    bounds_min: Vec3
    bounds_max: Vec3
    suggested_unit: LengthUnit
    noise: dict[str, float | None]
    proposed_tolerance: dict[str, float]
    reduction_required: bool
    counts: dict[str, int]


@command("mesh.import", caller="main")
def mesh_import(ctx: JobContext, params: ImportParams) -> ImportReport:
    """Load a mesh file into a pending import (called by the main process after a dialog)."""
    path = Path(params.path)
    session = ctx.session
    # Only the newest import can be confirmed; an older one would hold its mesh forever.
    session.pending_imports.clear()
    ctx.progress(None, ProgressStage.READING)
    loaded = read_mesh(path)
    ctx.check_cancelled()
    ctx.progress(None, ProgressStage.WELDING)
    welded, merged = weld_vertices(loaded)
    dropped = loaded.dropped_faces
    del loaded
    ctx.check_cancelled()
    ctx.progress(None, ProgressStage.ESTIMATING_NOISE)
    sha256 = _file_sha256(path)
    noise = _noise_per_unit(welded, seeded_rng(f"import-noise:{sha256}"), ctx.check_cancelled)
    pending = PendingImport(
        id=uuid.uuid4().hex[:12],
        file_name=path.name,
        sha256=sha256,
        mesh=welded,
        counts={"mergedVertices": merged, "nonFiniteFaces": dropped},
        noise=noise,
    )
    session.pending_imports[pending.id] = pending
    low, high = welded.vertices.min(axis=0), welded.vertices.max(axis=0)
    diagonal = float(np.linalg.norm(high - low))
    return ImportReport(
        pending_id=pending.id,
        file_name=pending.file_name,
        face_count=len(welded.faces),
        vertex_count=len(welded.vertices),
        bounds_min=vec3(low),
        bounds_max=vec3(high),
        suggested_unit="m" if diagonal < _METRES_BELOW_DIAGONAL else "mm",
        noise=dict(noise),
        proposed_tolerance={unit: propose_tolerance(value) for unit, value in noise.items()},
        reduction_required=len(welded.faces) > MAX_WORKING_FACES,
        counts=pending.counts,
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
    """Scale, repair, reduce if asked and make the pending import the scan of a new document.

    The project tolerance becomes the value the import panel proposed for the unit.
    """
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

    ctx.progress(0.05, ProgressStage.REPAIRING)
    prepared = repair(working, _IMPORT_REPAIR_STEPS)
    ctx.check_cancelled()
    ctx.progress(0.3, ProgressStage.REMOVING_SMALL_PARTS)
    prepared = prepared.then(
        remove_small_parts(prepared.mesh, DEFAULT_MIN_PART_RATIO, DEFAULT_MIN_PART_FACES)
    )
    ctx.check_cancelled()
    if target is not None and target < len(prepared.mesh.faces):
        prepared = prepared.then(_decimate(ctx, prepared.mesh, target))
    if len(prepared.mesh.faces) == 0:
        raise KernelError(ErrorCode.NOTHING_LEFT)
    counts = {**pending.counts, **prepared.counts}

    ctx.progress(0.9, ProgressStage.STORING)
    noise = pending.noise.get(params.unit)
    scan = _new_scan(
        session.blobs,
        prepared.mesh,
        prepared.synthetic,
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
    ctx.check_cancelled()
    snapshot = session.commit(document, "import", ctx)
    session.pending_imports.pop(pending.id, None)
    return CommitImportResult(revision=snapshot.revision, counts=counts)


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
    """Condition of the scan, shown in the scan information panel.

    Lengths in mm, areas in mm², volumes in mm³. `volume` is null unless the scan
    is closed (every edge has exactly two faces). `small_parts` counts the loose
    parts that *Kleine Teile entfernen* would remove with its default settings.
    """

    scan_key: str
    face_count: int
    vertex_count: int
    watertight: bool
    boundary_loops: int
    boundary_edges: int
    non_manifold_edges: int
    inconsistent_edges: int
    components: int
    small_parts: int
    degenerate_faces: int
    duplicate_faces: int
    synthetic_faces: int
    area: float
    volume: float | None
    size: Vec3
    noise: float | None


@command("mesh.inspect")
def mesh_inspect(ctx: JobContext, params: InspectParams) -> MeshReport:
    """Condition of the current scan: holes, defects, parts, area and volume."""
    scan, mesh = _current_scan(ctx)
    ctx.progress(None, ProgressStage.INSPECTING)
    topology = edge_topology(mesh.faces)
    loops = boundary_loops(mesh, topology)
    components, face_part = component_labels(mesh)
    ctx.check_cancelled()
    sizes = np.bincount(face_part, minlength=components)
    small = int(components - parts_to_keep(sizes).sum()) if components else 0
    _, areas = face_normals(mesh.vertices, mesh.faces)
    watertight = bool((topology.valence == 2).all())
    synthetic = ctx.session.blobs.get(scan.synthetic) if scan.synthetic is not None else None
    return MeshReport(
        scan_key=scan.key,
        face_count=len(mesh.faces),
        vertex_count=len(mesh.vertices),
        watertight=watertight,
        boundary_loops=len(loops.loops) + loops.skipped,
        boundary_edges=int((topology.valence == 1).sum()),
        non_manifold_edges=topology.non_manifold_edge_count,
        inconsistent_edges=topology.inconsistent_edge_count(),
        components=components,
        small_parts=small,
        degenerate_faces=remove_degenerate_faces(mesh).counts["degenerateFaces"],
        duplicate_faces=remove_duplicate_faces(mesh).counts["duplicateFaces"],
        synthetic_faces=0 if synthetic is None else int(np.count_nonzero(synthetic)),
        area=float(areas.sum()),
        volume=abs(signed_volume(mesh)) if watertight else None,
        size=vec3(np.ptp(mesh.vertices, axis=0)),
        noise=scan.noise,
    )


# --------------------------------------------------------------------------- preparation


@dataclass(frozen=True)
class MeshEditResult:
    """What a preparation step did or, for a dry run, would do.

    `changed` is false when the step finds nothing to do; then nothing is committed.
    `revision` is the new revision, or null for a dry run and for no change.
    `affected_faces` (dry runs only) are the faces of the current scan that the step
    removes or flips, or the faces around the holes it fills.
    """

    counts: dict[str, int]
    face_count: int
    vertex_count: int
    changed: bool
    revision: int | None
    affected_faces: U32Array


@dataclass(frozen=True)
class RepairParams:
    steps: tuple[RepairStep, ...] = REPAIR_STEPS
    dry_run: bool = False


@command("mesh.repair", lane=True)
def mesh_repair(ctx: JobContext, params: RepairParams) -> MeshEditResult:
    """Weld, remove degenerate and duplicate faces, fix the winding, turn parts outward."""
    return _edit(ctx, "repair", params.dry_run, lambda mesh: repair(mesh, params.steps))


@dataclass(frozen=True)
class RemoveSmallPartsParams:
    min_ratio: Annotated[float, Range(0.0, 1.0)] = DEFAULT_MIN_PART_RATIO
    min_faces: Annotated[int, Range(0, 1_000_000)] = DEFAULT_MIN_PART_FACES
    dry_run: bool = False


@command("mesh.removeSmallParts", lane=True)
def mesh_remove_small_parts(ctx: JobContext, params: RemoveSmallPartsParams) -> MeshEditResult:
    """Remove loose parts (debris, fixtures) below a share of the largest part."""
    return _edit(
        ctx,
        "removeSmallParts",
        params.dry_run,
        lambda mesh: remove_small_parts(mesh, params.min_ratio, params.min_faces),
    )


@dataclass(frozen=True)
class FillHolesParams:
    max_perimeter: Annotated[float, Range(0.0, 100_000.0)]
    dry_run: bool = False


@command("mesh.fillHoles", lane=True)
def mesh_fill_holes(ctx: JobContext, params: FillHolesParams) -> MeshEditResult:
    """Close holes up to a perimeter; the new faces are marked synthetic and never fitted."""
    ctx.progress(None, ProgressStage.FILLING_HOLES)
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

    A dry run reports the counts only; the reduction itself takes seconds and
    runs alone (exclusive), with cancellation.
    """
    if params.dry_run:
        _, mesh = _current_scan(ctx)
        after = min(params.target_faces, len(mesh.faces))
        counts = {"facesBefore": len(mesh.faces), "facesAfter": after}
        changed = after < len(mesh.faces)
        return MeshEditResult(counts, after, len(mesh.vertices), changed, None, _NO_FACES)
    return _edit(ctx, "decimate", False, lambda mesh: _decimate(ctx, mesh, params.target_faces))


@dataclass(frozen=True)
class DeleteFacesParams:
    faces: U32Array
    scan_key: str


@command("mesh.deleteFaces")
def mesh_delete_faces(ctx: JobContext, params: DeleteFacesParams) -> MeshEditResult:
    """Delete selected faces; a selection made on another scan is rejected."""
    scan, mesh = _current_scan(ctx)
    faces = np.asarray(params.faces, dtype=np.int64)
    if params.scan_key != scan.key or (len(faces) and int(faces.max()) >= len(mesh.faces)):
        raise KernelError(ErrorCode.STALE_SELECTION, {"scanKey": params.scan_key})
    return _edit(ctx, "deleteFaces", False, lambda current: delete_faces(current, faces))


@dataclass(frozen=True)
class SetSmoothingParams:
    iterations: Annotated[int, Range(0, MAX_ITERATIONS)]


@dataclass(frozen=True)
class SetSmoothingResult:
    revision: int | None


@command("mesh.setSmoothing")
def mesh_set_smoothing(ctx: JobContext, params: SetSmoothingParams) -> SetSmoothingResult:
    """Display smoothing of the scan (Taubin); fits always use the unsmoothed scan."""
    scan, _ = _current_scan(ctx)
    if scan.display_smoothing == params.iterations:
        return SetSmoothingResult(revision=None)
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


def _noise_per_unit(
    mesh: RawMesh, rng: np.random.Generator, check_cancelled: Callable[[], None]
) -> dict[str, float | None]:
    """Noise in mm for every unit the file could be in.

    The jet fit works at a physical scale (`DEFAULT_CELL_MM`), so the estimate
    depends on the unit. Units are tried from the coarsest cell to the finest;
    once the cell is below the vertex spacing every finer cell gives the same
    neighbourhoods, and the earlier estimate is reused.
    """
    normals = vertex_normals(mesh.vertices, mesh.faces)
    noise: dict[str, float | None] = {}
    fine: NoiseEstimate | None = None
    for unit, scale in sorted(UNIT_SCALE.items(), key=lambda item: item[1]):
        check_cancelled()
        estimate = fine or estimate_noise(mesh.vertices, normals, rng, DEFAULT_CELL_MM / scale)
        if estimate.sample_share >= _FINE_SAMPLE_SHARE:
            fine = estimate
        noise[unit] = None if estimate.noise is None else estimate.noise * scale
    return noise


def _edit(
    ctx: JobContext, op: str, dry_run: bool, operation: Callable[[RawMesh], MeshChange]
) -> MeshEditResult:
    scan, mesh = _current_scan(ctx)
    change = operation(mesh)
    ctx.check_cancelled()
    result = change.mesh
    if len(result.faces) == 0:
        raise KernelError(ErrorCode.NOTHING_LEFT)
    changed = not (
        np.array_equal(result.faces, mesh.faces) and np.array_equal(result.vertices, mesh.vertices)
    )
    revision = _commit_change(ctx, scan, change, op) if changed and not dry_run else None
    affected = change.affected.astype(np.uint32) if dry_run else _NO_FACES
    return MeshEditResult(
        change.counts, len(result.faces), len(result.vertices), changed, revision, affected
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
    has_source = change.new_to_old >= 0
    source = np.where(has_source, change.new_to_old, 0)
    synthetic = change.synthetic.copy()
    if scan.synthetic is not None:
        synthetic |= has_source & blobs.get(scan.synthetic).astype(bool)[source]
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
    remap = _FaceSetRemap(blobs, change.new_to_old, scan.face_count)
    document = replace(
        document,
        scan=new_scan,
        regions=_remap_regions(document.regions, blobs, change),
        features=tuple(
            replace(feature, params=remap(feature.params)) for feature in document.features
        ),
        alignment=replace(document.alignment, params=remap(document.alignment.params)),
    )
    return session.commit(document, op, ctx).revision


class _FaceSetRemap:
    """Carries every face set (a 1-D uint32 blob) inside parameter JSON to the new scan."""

    def __init__(self, blobs: BlobStore, new_to_old: npt.NDArray[np.int64], old_faces: int):
        self._blobs = blobs
        self._new_to_old = new_to_old
        self._old_faces = old_faces
        self._done: dict[BlobRef, BlobRef] = {}

    def __call__(self, value: JsonValue) -> JsonValue:
        if isinstance(value, str) and value.startswith("blob:"):
            return self._face_set(value)
        if isinstance(value, list):
            return [self(item) for item in value]
        if isinstance(value, dict):
            return {key: self(item) for key, item in value.items()}
        return value

    def _face_set(self, ref: BlobRef) -> BlobRef:
        if ref not in self._done:
            array = self._blobs.get(ref)
            if array.ndim == 1 and array.dtype == np.uint32:
                faces = remap_face_set(array.astype(np.int64), self._new_to_old, self._old_faces)
                self._done[ref] = self._blobs.put(faces.astype(np.uint32))
            else:
                self._done[ref] = ref
        return self._done[ref]


def _remap_regions(regions: Regions, blobs: BlobStore, change: MeshChange) -> Regions:
    """Labels through the face map; face counts and areas are recounted, empty regions go."""
    if regions.labels is None:
        return regions
    labels = remap_labels(blobs.get(regions.labels).astype(np.uint16), change.new_to_old)
    size = max((item.label for item in regions.items), default=0) + 1
    counts = np.bincount(labels, minlength=size)
    _, areas = face_normals(change.mesh.vertices, change.mesh.faces)
    area = np.bincount(labels, weights=areas, minlength=size)
    items = tuple(
        replace(item, face_count=int(counts[item.label]), area=float(area[item.label]))
        for item in regions.items
        if counts[item.label] > 0
    )
    return Regions(labels=blobs.put(labels), items=items)


def _new_scan(
    blobs: BlobStore,
    mesh: RawMesh,
    synthetic: npt.NDArray[np.bool_],
    *,
    source: ScanSource,
    origin: npt.NDArray[np.float64],
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
