"""Public API of STEP and STL export.

STEP is written with XCAF, so every body becomes one product with exactly the given
name (the plain writer appends an instance number), in millimetres and with an
explicit schema. Files are written to a temporary file next to the target, checked,
and only then renamed over the target, so a failed export never touches an existing
file. The STEP check reads the file back and compares validity, solid count and
volume (relative error at most 1e-6; measured 4e-15). Details:
`.work/research/algorithms-cad.md` section 5.
"""

from __future__ import annotations

import contextlib
import os
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import trimesh

# OCP names missing from cad/occ_compat.py; see .work/interface-requests/T7.md.
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from m2c_kernel.cad.check import SolidCheck, check_solid
from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    Standard_Failure,
    TopAbs_ShapeEnum,
    TopExp_Explorer,
    TopoDS_Shape,
)
from m2c_kernel.cad.tessellate import tessellate
from m2c_kernel.codes.export import ErrorCode, IssueCode
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.fs import replace_with_retry

type StepSchema = Literal["AP214", "AP242"]

STEP_SCHEMAS: dict[StepSchema, str] = {"AP214": "AP214IS", "AP242": "AP242DIS"}
MAX_VOLUME_ERROR = 1e-6
STL_ANGULAR_DEFLECTION_RAD = 0.2
STL_HEADER = b"Mesh-to-CAD binary STL, millimetres"
_STL_HEADER_BYTES = 84
_STL_TRIANGLE_BYTES = 50


@dataclass(frozen=True)
class BodyCheck:
    """Pre-flight result of one body. Every problem except a high tolerance blocks export."""

    valid: bool
    closed: bool
    solids: int
    volume: float
    area: float
    max_tolerance: float
    problems: tuple[IssueCode, ...]

    @property
    def blocking(self) -> bool:
        """Whether a problem prevents the export."""
        return any(problem != IssueCode.HIGH_TOLERANCE for problem in self.problems)


@dataclass(frozen=True)
class StepCheck:
    """Comparison of a written STEP file with the exported bodies."""

    valid: bool
    solids: int
    expected_solids: int
    volume_error: float

    @property
    def passed(self) -> bool:
        """Valid, the same solid count and the same volume within `MAX_VOLUME_ERROR`."""
        return (
            self.valid
            and self.solids == self.expected_solids
            and self.volume_error <= MAX_VOLUME_ERROR
        )


@dataclass(frozen=True)
class WrittenFile:
    """Size of a written file and, for STL, its triangle count."""

    bytes: int
    triangles: int | None = None


def check_body(body: Body) -> BodyCheck:
    """Validity, closed shells, one solid, positive volume and vertex tolerances."""
    check = check_solid(body.shape)
    closed = _shells_closed(body.shape)
    problems: list[IssueCode] = []
    if not check.valid:
        problems.append(IssueCode.NOT_VALID)
    if not closed:
        problems.append(IssueCode.NOT_CLOSED)
    if check.solids != 1:
        problems.append(IssueCode.NOT_ONE_SOLID)
    if not check.volume > 0.0:
        problems.append(IssueCode.NO_VOLUME)
    if check.high_tolerance:
        problems.append(IssueCode.HIGH_TOLERANCE)
    return BodyCheck(
        valid=check.valid,
        closed=closed,
        solids=check.solids,
        volume=check.volume,
        area=check.area,
        max_tolerance=check.max_tolerance,
        problems=tuple(problems),
    )


def _shells_closed(shape: TopoDS_Shape) -> bool:
    explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SHELL)
    shells = 0
    while explorer.More():
        if not BRep_Tool.IsClosed_s(explorer.Current()):
            return False
        shells += 1
        explorer.Next()
    return shells > 0


def write_step(
    path: Path, bodies: Sequence[tuple[str, Body]], schema: StepSchema = "AP214"
) -> tuple[WrittenFile, StepCheck]:
    """Write (product name, body) pairs to STEP and verify the file by reading it back.

    Raises `KernelError` (`export.writeFailed`, `export.verifyFailed`); the target is
    replaced only after the check passed.
    """
    temporary = _temporary(path)
    try:
        try:
            _write_step_file(temporary, bodies, schema)
        except Standard_Failure as failure:
            raise KernelError(ErrorCode.WRITE_FAILED, details=str(failure)) from failure
        check = verify_step(temporary, [body for _, body in bodies])
        if not check.passed:
            raise KernelError(
                ErrorCode.VERIFY_FAILED,
                {"volumeError": check.volume_error, "solids": check.solids},
                details=f"STEP read-back differs: {check}",
            )
        size = temporary.stat().st_size
        _replace(temporary, path)
        return WrittenFile(bytes=size), check
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _write_step_file(path: Path, bodies: Sequence[tuple[str, Body]], schema: StepSchema) -> None:
    STEPControl_Controller.Init_s()  # registers the write.step.* parameters
    for key, value in (("write.step.schema", STEP_SCHEMAS[schema]), ("write.step.unit", "MM")):
        if not Interface_Static.SetCVal_s(key, value):
            raise KernelError(ErrorCode.WRITE_FAILED, details=f"STEP parameter rejected: {key}")
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    for name, body in bodies:
        label = shape_tool.AddShape(body.shape, False)
        # True: the name is UTF-8, so umlauts survive.
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name, True))
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise KernelError(ErrorCode.WRITE_FAILED, details="STEP transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise KernelError(ErrorCode.WRITE_FAILED, details=f"STEP write failed: {path.name}")


def read_step(path: Path) -> TopoDS_Shape:
    """Read a STEP file into one shape (a compound when it holds several solids)."""
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise KernelError(ErrorCode.VERIFY_FAILED, details=f"STEP read failed: {path.name}")
    reader.TransferRoots()
    return reader.OneShape()


def verify_step(path: Path, bodies: Sequence[Body]) -> StepCheck:
    """Re-read a written STEP file and compare it with the exported bodies."""
    loaded = check_solid(read_step(path))
    checks: list[SolidCheck] = [check_solid(body.shape) for body in bodies]
    expected_volume = sum(check.volume for check in checks)
    error = abs(loaded.volume - expected_volume) / max(abs(expected_volume), 1e-300)
    return StepCheck(
        valid=loaded.valid,
        solids=loaded.solids,
        expected_solids=sum(check.solids for check in checks),
        volume_error=float(error),
    )


def write_stl(path: Path, bodies: Sequence[Body], deflection: float) -> WrittenFile:
    """Write the tessellated bodies to one binary STL; the target is replaced when complete.

    The triangles come from `cad.tessellate` and are welded before writing, so shared
    edges have bit-identical float32 corners and the file loads watertight. The file is
    written from Python because OCCT's STL writer fails on paths with umlauts.
    """
    records = np.concatenate([_stl_records(body.shape, deflection) for body in bodies])
    temporary = _temporary(path)
    try:
        header = STL_HEADER.ljust(80, b" ") + struct.pack("<I", len(records))
        try:
            with temporary.open("wb") as stream:
                stream.write(header)
                stream.write(records.tobytes())
        except OSError as failure:
            raise KernelError(ErrorCode.WRITE_FAILED, details=str(failure)) from failure
        triangles = _stl_triangle_count(temporary)
        size = temporary.stat().st_size
        _replace(temporary, path)
        return WrittenFile(bytes=size, triangles=triangles)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])


def _stl_records(shape: TopoDS_Shape, deflection: float) -> npt.NDArray[np.void]:
    tessellation = tessellate(shape, deflection, STL_ANGULAR_DEFLECTION_RAD)
    mesh = trimesh.Trimesh(tessellation.vertices, tessellation.triangles, process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    records = np.zeros(len(mesh.faces), dtype=_STL_RECORD)
    records["normal"] = mesh.face_normals
    records["corners"] = np.asarray(mesh.vertices, dtype=np.float32)[mesh.faces]
    return records


def _stl_triangle_count(path: Path) -> int:
    """Triangle count of a binary STL; fails unless the header matches the file size."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(_STL_HEADER_BYTES)
    count = struct.unpack("<I", header[80:84])[0] if len(header) == _STL_HEADER_BYTES else 0
    if count == 0 or size != _STL_HEADER_BYTES + _STL_TRIANGLE_BYTES * count:
        raise KernelError(
            ErrorCode.VERIFY_FAILED, details=f"STL has {size} bytes for {count} triangles"
        )
    return int(count)


def _replace(temporary: Path, target: Path) -> None:
    try:
        replace_with_retry(temporary, target)
    except OSError as failure:
        raise KernelError(ErrorCode.WRITE_FAILED, details=str(failure)) from failure


def _temporary(path: Path) -> Path:
    """A temporary file next to the target (same volume, so the final rename is atomic)."""
    return path.with_name(f".{path.stem}.{os.getpid()}.tmp{path.suffix}")
