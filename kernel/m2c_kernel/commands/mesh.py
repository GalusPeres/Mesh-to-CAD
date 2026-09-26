"""Mesh import and preparation.

Import has two phases so that the file path stays in the main process while
the renderer asks for the unit: `mesh.import` (main process only) loads the
file into a pending import and returns a report; `mesh.commitImport` or
`mesh.discardImport` follows from the import panel.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from m2c_kernel.codes.kernel import ErrorCode as KernelErrorCode
from m2c_kernel.codes.mesh import ErrorCode, ProgressStage
from m2c_kernel.document.model import (
    Document,
    DocumentSettings,
    LengthUnit,
    Scan,
    ScanOperation,
    ScanSource,
)
from m2c_kernel.geometry import Vec3, vec3
from m2c_kernel.limits import DEFAULT_TOLERANCE_MM, MAX_WORKING_FACES
from m2c_kernel.mesh.load import PendingImport, RawMesh, read_mesh, weld_vertices
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext

UNIT_SCALE: dict[LengthUnit, float] = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
_TOLERANCE_STEPS_MM = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class ImportParams:
    path: str


@dataclass(frozen=True)
class ImportReport:
    """What the import panel shows before the user confirms the unit.

    Bounds are in file units. `suggested_unit` is a guess (a part smaller than two
    units is almost certainly in metres); the user always confirms.
    """

    pending_id: str
    file_name: str
    face_count: int
    vertex_count: int
    merged_vertices: int
    bounds_min: Vec3
    bounds_max: Vec3
    suggested_unit: LengthUnit
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
        requires_reduction=len(welded.faces) > MAX_WORKING_FACES,
    )


@dataclass(frozen=True)
class CommitImportParams:
    pending_id: str
    unit: LengthUnit
    reduce_to: int | None = None


@dataclass(frozen=True)
class CommitImportResult:
    revision: int


@command("mesh.commitImport")
def mesh_commit_import(ctx: JobContext, params: CommitImportParams) -> CommitImportResult:
    """Scale the pending import, estimate its noise and make it the scan of a new document."""
    session = ctx.session
    pending = session.pending_imports.get(params.pending_id)
    if pending is None:
        raise KernelError(ErrorCode.UNKNOWN_IMPORT, {"pendingId": params.pending_id})
    mesh = pending.mesh
    if params.reduce_to is not None:
        raise KernelError(KernelErrorCode.NOT_IMPLEMENTED, {"method": "mesh.commitImport.reduceTo"})
    if len(mesh.faces) > MAX_WORKING_FACES:
        raise KernelError(
            ErrorCode.REDUCTION_REQUIRED, {"faces": len(mesh.faces), "maxFaces": MAX_WORKING_FACES}
        )

    vertices = mesh.vertices * UNIT_SCALE[params.unit]
    ctx.progress(0.5, ProgressStage.ESTIMATING_NOISE)
    noise = _estimate_noise(RawMesh(vertices, mesh.faces))
    ctx.check_cancelled()

    low, high = vertices.min(axis=0), vertices.max(axis=0)
    origin = (low + high) / 2.0
    blobs = session.blobs
    vertices_ref = blobs.put((vertices - origin).astype(np.float32))
    faces_ref = blobs.put(mesh.faces.astype(np.uint32))
    scan_key = hashlib.sha256(f"{vertices_ref}|{faces_ref}".encode()).hexdigest()[:24]
    scan = Scan(
        key=f"scan:{scan_key}",
        source=ScanSource(
            file_name=pending.file_name, sha256=pending.sha256, import_unit=params.unit
        ),
        vertices=vertices_ref,
        faces=faces_ref,
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(mesh.faces),
        origin=vec3(origin),
        noise=noise,
        operations=(
            ScanOperation(op="import", counts={"mergedVertices": pending.merged_vertices}),
        ),
    )
    document = replace(
        Document.empty(),
        scan=scan,
        settings=DocumentSettings(tolerance=propose_tolerance(noise)),
    )
    snapshot = session.commit(document, "import", ctx)
    del session.pending_imports[pending.id]
    return CommitImportResult(revision=snapshot.revision)


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


def propose_tolerance(noise: float | None) -> float:
    """Project tolerance proposed from the scan noise: the first step at or above 2.5 sigma."""
    if noise is None or not np.isfinite(noise):
        return DEFAULT_TOLERANCE_MM
    wanted = 2.5 * noise
    return next((step for step in _TOLERANCE_STEPS_MM if step >= wanted), _TOLERANCE_STEPS_MM[-1])


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
