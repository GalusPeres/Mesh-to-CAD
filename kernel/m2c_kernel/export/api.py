"""Public API of STEP and STL export.

STEP is written with XCAF (exact product names), unit millimetre and an explicit
schema, to a temporary file that is read back and compared (valid, solid count,
volume) before it replaces the target, so a failed export never touches an
existing file. Measurements: `.work/research/algorithms-cad.md` section 5.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Not (yet) re-exported by cad/occ_compat.py; see .work/interface-requests/T7.md.
from OCP.BRep import BRep_Builder
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Reader
from OCP.StlAPI import StlAPI_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import BRepMesh_IncrementalMesh, BRepTools, TopoDS_Shape
from m2c_kernel.document.results import Body
from m2c_kernel.session.fs import replace_with_retry

type StepSchema = Literal["AP214", "AP242"]

STEP_SCHEMAS: dict[StepSchema, str] = {"AP214": "AP214IS", "AP242": "AP242DIS"}
MAX_VOLUME_ERROR = 1e-6
STL_ANGULAR_DEFLECTION_RAD = 0.2


class ExportError(RuntimeError):
    """Writing failed (`stage` = "write") or the file did not verify (`stage` = "verify")."""

    def __init__(self, stage: Literal["write", "verify"], details: str) -> None:
        super().__init__(details)
        self.stage = stage


@dataclass(frozen=True)
class StepCheck:
    """Comparison of a written STEP file with the exported bodies."""

    valid: bool
    solids: int
    expected_solids: int
    volume_error: float

    @property
    def passed(self) -> bool:
        """Whether the re-read file matches the exported bodies."""
        return (
            self.valid
            and self.solids == self.expected_solids
            and self.volume_error <= MAX_VOLUME_ERROR
        )


def write_step(
    path: Path, bodies: Mapping[str, Body], names: Mapping[str, str], schema: StepSchema
) -> StepCheck:
    """Write bodies to STEP (one named product per body) and verify the file by reading it back.

    `names` maps body ids to product names. Raises `ExportError`; the target is replaced only
    after the check passed.
    """
    temporary = _temporary(path)
    try:
        _write_step_file(temporary, bodies, names, schema)
        check = verify_step(temporary, bodies)
        if not check.passed:
            raise ExportError("verify", f"STEP read-back differs: {check}")
        replace_with_retry(temporary, path)
        return check
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _write_step_file(
    path: Path, bodies: Mapping[str, Body], names: Mapping[str, str], schema: StepSchema
) -> None:
    STEPControl_Controller.Init_s()  # registers the write.step.* parameters
    for key, value in (("write.step.schema", STEP_SCHEMAS[schema]), ("write.step.unit", "MM")):
        if not Interface_Static.SetCVal_s(key, value):
            raise ExportError("write", f"STEP parameter rejected: {key}={value}")
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    for body_id, body in bodies.items():
        label = shape_tool.AddShape(body.shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(names.get(body_id, body_id)))
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise ExportError("write", "STEP transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise ExportError("write", f"STEP write failed: {path}")


def read_step(path: Path) -> TopoDS_Shape:
    """Read a STEP file into one shape."""
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ExportError("verify", f"STEP read failed: {path}")
    reader.TransferRoots()
    return reader.OneShape()


def verify_step(path: Path, bodies: Mapping[str, Body]) -> StepCheck:
    """Re-read a written STEP file and compare it with the exported bodies."""
    loaded = check_solid(read_step(path))
    checks = [check_solid(body.shape) for body in bodies.values()]
    expected_volume = sum(check.volume for check in checks)
    error = abs(loaded.volume - expected_volume) / max(abs(expected_volume), 1e-300)
    return StepCheck(
        valid=loaded.valid,
        solids=loaded.solids,
        expected_solids=sum(check.solids for check in checks),
        volume_error=float(error),
    )


def write_stl(path: Path, bodies: Mapping[str, Body], deflection: float) -> None:
    """Write the tessellated bodies to one binary STL (replaces the target when complete)."""
    compound = _compound([body.shape for body in bodies.values()])
    BRepTools.Clean_s(compound)
    BRepMesh_IncrementalMesh(compound, deflection, False, STL_ANGULAR_DEFLECTION_RAD, True)
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    temporary = _temporary(path)
    try:
        if not writer.Write(compound, str(temporary)):
            raise ExportError("write", f"STL write failed: {path}")
        replace_with_retry(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _compound(shapes: list[Any]) -> TopoDS_Compound:
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _temporary(path: Path) -> Path:
    """A temporary file next to the target (same volume, so the final rename is atomic)."""
    return path.with_name(f".{path.stem}.{os.getpid()}.tmp{path.suffix}")
