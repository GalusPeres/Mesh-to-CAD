"""STEP and STL export of bodies.

`export.preflight` tells the export panel which bodies can be written and why not.
`export.step` and `export.stl` take the target path and are therefore called only by
the main process, after the save dialog (file actions `exportStep`, `exportStl`).
Both refuse bodies that fail the pre-flight check, write to a temporary file, check
it and only then replace the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from m2c_kernel.codes.export import ErrorCode, IssueCode, ProgressStage
from m2c_kernel.document.results import Body
from m2c_kernel.export.api import StepSchema, check_body, write_step, write_stl
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
class PreflightResult:
    bodies: list[BodyPreflight]
    exportable: bool


@command("export.preflight")
def export_preflight(ctx: JobContext, params: PreflightParams) -> PreflightResult:
    """Check the bodies before an export: valid, closed, one solid, volume, tolerances."""
    built = ctx.session.built(ctx)
    reports = [_preflight(built, body_id, body) for body_id, body in _bodies(built, params.bodies)]
    return PreflightResult(
        bodies=reports, exportable=bool(reports) and not any(r.blocking for r in reports)
    )


@dataclass(frozen=True)
class StepParams:
    path: str
    bodies: list[str]
    names: list[str]
    """Product name per body, in the order of `bodies` (the project name)."""
    schema: StepSchema = "AP214"


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


@command("export.step", caller="main")
def export_step(ctx: JobContext, params: StepParams) -> ExportResult:
    """Write the bodies as STEP (millimetres), read the file back and compare, then save."""
    built = ctx.session.built(ctx)
    bodies = _exportable(built, params.bodies)
    names = [name.strip() for name in params.names]
    if len(names) != len(bodies) or any(not 0 < len(name) <= MAX_NAME_LENGTH for name in names):
        raise KernelError(ErrorCode.INVALID_NAMES)
    path = Path(params.path)
    with ctx.native(ProgressStage.WRITING):
        written, _ = write_step(
            path,
            [(name, body) for name, (_, body) in zip(names, bodies, strict=True)],
            params.schema,
        )
    return ExportResult(
        file_name=path.name, bytes=written.bytes, bodies=len(bodies), triangles=None
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
