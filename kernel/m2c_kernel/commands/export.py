"""STEP and STL export of bodies (and, in STEP, open surfaces).

`export.preflight` tells the export panel which bodies can be written and why not, and
which open surfaces (open freeform nets) STEP can carry along.
`export.step` and `export.stl` take the target path and are therefore called only by
the main process, after the save dialog (file actions `exportStep`, `exportStl`).
Both refuse bodies that fail the pre-flight check, write to a temporary file, check
it and only then replace the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from m2c_kernel.cad.occ_compat import BRepCheck_Analyzer, TopoDS_Shape
from m2c_kernel.codes.export import ErrorCode, IssueCode, ProgressStage
from m2c_kernel.document.results import Body
from m2c_kernel.export.api import StepSchema, check_body, face_count, write_step, write_stl
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import Range
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import BuiltDocument

MAX_NAME_LENGTH = 200


@dataclass(frozen=True)
class PreflightParams:
    bodies: list[str]
    """Body ids; empty checks every body."""


@dataclass(frozen=True)
class BodyPreflight:
    """`owner` is the feature that produced the body's current shape (the cause of problems)."""

    body: str
    owner: str
    valid: bool
    closed: bool
    solids: int
    volume: float
    max_tolerance: float
    problems: list[str]
    """Issue codes (`export.notClosed`, ...); all but `export.highTolerance` block."""
    blocking: bool


@dataclass(frozen=True)
class SurfacePreflight:
    """An open surface STEP can carry: the feature that made it, its faces, validity."""

    feature: str
    faces: int
    valid: bool


@dataclass(frozen=True)
class PreflightResult:
    bodies: list[BodyPreflight]
    exportable: bool
    surfaces: list[SurfacePreflight] = field(default_factory=list)
    """Open freeform nets; STEP export may carry them along."""


@command("export.preflight")
def export_preflight(ctx: JobContext, params: PreflightParams) -> PreflightResult:
    """Check the bodies before an export: valid, closed, one solid, volume, tolerances."""
    built = ctx.session.built(ctx)
    open_surfaces = _open_surfaces(built)
    # With open surfaces and no bodies there is still something to export.
    present = params.bodies or built.result.bodies or not open_surfaces
    pairs = _bodies(built, params.bodies) if present else []
    reports = [_preflight(built, body_id, body) for body_id, body in pairs]
    surfaces = [
        SurfacePreflight(
            feature=feature_id,
            faces=face_count(shape),
            valid=bool(BRepCheck_Analyzer(shape).IsValid()),
        )
        for feature_id, shape in open_surfaces
    ]
    exportable = bool(reports) and not any(r.blocking for r in reports)
    return PreflightResult(bodies=reports, exportable=exportable, surfaces=surfaces)


@dataclass(frozen=True)
class StepParams:
    path: str
    bodies: list[str]
    names: list[str]
    """Product name per body, in the order of `bodies` (the project name)."""
    schema: StepSchema = "AP214"
    surfaces: list[str] = field(default_factory=list)
    """Features whose open surface is written too (open freeform nets)."""
    surface_names: list[str] = field(default_factory=list)
    """Name per surface, in the order of `surfaces`."""


@dataclass(frozen=True)
class StlParams:
    path: str
    bodies: list[str]
    deflection: Annotated[float, Range(0.001, 1.0)] = 0.01
    """Largest distance between the triangles and the exact surface (mm)."""


@dataclass(frozen=True)
class ExportResult:
    file_name: str
    bytes: int
    bodies: int
    triangles: int | None
    """Triangles written (STL only)."""
    surfaces: int = 0
    """Open surfaces written (STEP only)."""


@command("export.step", caller="main")
def export_step(ctx: JobContext, params: StepParams) -> ExportResult:
    """Write the bodies as STEP (millimetres), read the file back and compare, then save."""
    built = ctx.session.built(ctx)
    # Only surfaces: no bodies (an empty list would otherwise mean every body).
    bodies = _exportable(built, params.bodies) if params.bodies or not params.surfaces else []
    surfaces = _chosen_surfaces(built, params.surfaces)
    names = [name.strip() for name in params.names]
    surface_names = [name.strip() for name in params.surface_names]
    if (
        len(names) != len(bodies)
        or len(surface_names) != len(surfaces)
        or any(not 0 < len(name) <= MAX_NAME_LENGTH for name in names + surface_names)
    ):
        raise KernelError(ErrorCode.INVALID_NAMES)
    path = Path(params.path)
    with ctx.native(ProgressStage.WRITING):
        written, _ = write_step(
            path,
            [(name, body) for name, (_, body) in zip(names, bodies, strict=True)],
            params.schema,
            [(name, shape) for name, shape in zip(surface_names, surfaces, strict=True)],
        )
    return ExportResult(
        file_name=path.name,
        bytes=written.bytes,
        bodies=len(bodies),
        triangles=None,
        surfaces=len(surfaces),
    )


@command("export.stl", caller="main")
def export_stl(ctx: JobContext, params: StlParams) -> ExportResult:
    """Write the tessellated bodies as one binary STL."""
    built = ctx.session.built(ctx)
    bodies = _exportable(built, params.bodies)
    path = Path(params.path)
    with ctx.native(ProgressStage.WRITING):
        written = write_stl(path, [body for _, body in bodies], params.deflection)
    return ExportResult(
        file_name=path.name, bytes=written.bytes, bodies=len(bodies), triangles=written.triangles
    )


def _bodies(built: BuiltDocument, ids: list[str]) -> list[tuple[str, Body]]:
    bodies = built.result.bodies
    wanted = ids or list(bodies)
    if not wanted:
        raise KernelError(ErrorCode.NO_BODY)
    missing = [body_id for body_id in wanted if body_id not in bodies]
    if missing:
        raise KernelError(ErrorCode.UNKNOWN_BODY, {"body": missing[0]})
    return [(body_id, bodies[body_id]) for body_id in wanted]


def _open_surfaces(built: BuiltDocument) -> list[tuple[str, TopoDS_Shape]]:
    """Open freeform nets (their surfaces), in history order."""
    surfaces = []
    for feature in built.document.features:
        output = built.result.outputs.get(feature.id)
        surface = output.construction.surface if output and output.construction else None
        if feature.type == "freeformNet" and surface is not None:
            surfaces.append((feature.id, surface))
    return surfaces


def _chosen_surfaces(built: BuiltDocument, ids: list[str]) -> list[TopoDS_Shape]:
    available = dict(_open_surfaces(built))
    missing = [feature for feature in ids if feature not in available]
    if missing:
        raise KernelError(ErrorCode.UNKNOWN_SURFACE, {"surface": missing[0]})
    return [available[feature] for feature in ids]


def _preflight(built: BuiltDocument, body_id: str, body: Body) -> BodyPreflight:
    check = check_body(body)
    return BodyPreflight(
        body=body_id,
        owner=built.result.body_owner[body_id],
        valid=check.valid,
        closed=check.closed,
        solids=check.solids,
        volume=check.volume,
        max_tolerance=check.max_tolerance,
        problems=[str(problem) for problem in check.problems],
        blocking=check.blocking,
    )


def _exportable(built: BuiltDocument, ids: list[str]) -> list[tuple[str, Body]]:
    bodies = _bodies(built, ids)
    for body_id, body in bodies:
        report = _preflight(built, body_id, body)
        if report.blocking:
            problem = next(p for p in report.problems if p != IssueCode.HIGH_TOLERANCE)
            raise KernelError(
                ErrorCode.BLOCKED, {"body": body_id, "feature": report.owner, "problem": problem}
            )
    return bodies
