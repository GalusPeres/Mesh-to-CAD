"""STEP and STL export: file content, read-back, untouched targets on failure."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import trimesh
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool

import m2c_kernel.commands.export as export_commands
import m2c_kernel.export.api as export_api
from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepBuilderAPI_Transform,
    BRepPrimAPI_MakeBox,
    TopAbs_FACE,
    TopExp_Explorer,
    gp_Trsf,
    gp_Vec,
)
from m2c_kernel.codes.export import ErrorCode, IssueCode
from m2c_kernel.commands.export import (
    PreflightParams,
    StepParams,
    StlParams,
    export_preflight,
    export_step,
    export_stl,
)
from m2c_kernel.document.results import Body
from m2c_kernel.export.api import (
    BodyCheck,
    StepCheck,
    check_body,
    read_step,
    write_step,
    write_stl,
)
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import load_commands
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.inspection.scene import (
    _block_shape,
    commit,
    feature,
    noisy_block,
    registered_types,
    scan_document,
)

pytestmark = pytest.mark.occt

SCHEMA_NAMES = {
    "AP214": "AUTOMOTIVE_DESIGN",
    "AP242": "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF",
}


def _block() -> Body:
    return Body(_block_shape())


def _moved_box(offset: float) -> Body:
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(offset, 0.0, 0.0))
    box = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
    return Body(BRepBuilderAPI_Transform(box, transform, True).Shape())


@pytest.mark.parametrize("schema", ["AP214", "AP242"])
def test_step_has_millimetres_schema_and_exact_names(tmp_path: Path, schema: str) -> None:
    target = tmp_path / "halterung.step"
    written, check = write_step(target, [("Halterung", _block())], schema)  # type: ignore[arg-type]
    text = target.read_bytes().decode("utf-8")
    assert "SI_UNIT(.MILLI.,.METRE.)" in text
    schema_entry = re.search(r"FILE_SCHEMA\(\(\s*'([^']*)'", text)
    assert schema_entry is not None and SCHEMA_NAMES[schema] in schema_entry.group(1)
    assert re.findall(r"PRODUCT\('([^']*)'", text) == ["Halterung"]
    assert written.bytes == target.stat().st_size
    assert check.passed and check.volume_error < 1e-9


def test_step_round_trip_keeps_volume_and_solids(tmp_path: Path) -> None:
    bodies = [_block(), _moved_box(150.0)]
    target = tmp_path / "zwei.step"
    write_step(target, [("Teil Körper 1", bodies[0]), ("Teil Körper 2", bodies[1])])
    loaded = check_solid(read_step(target))
    expected = sum(check_solid(body.shape).volume for body in bodies)
    assert loaded.valid and loaded.solids == 2
    assert abs(loaded.volume - expected) / expected < 1e-9
    assert _xcaf_names_equal(target, ["Teil Körper 1", "Teil Körper 2"])


def _xcaf_names_equal(path: Path, expected: list[str]) -> bool:
    """Whether the free shapes of the file carry exactly these names (read with XCAF)."""
    from OCP.collections import Sequence_TDF_Label

    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.ReadFile(str(path))
    assert reader.Transfer(document)
    labels = Sequence_TDF_Label()
    XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).GetFreeShapes(labels)
    if labels.Length() != len(expected):
        return False
    for index, text in enumerate(expected, start=1):
        name = TDataStd_Name()
        assert labels.Value(index).FindAttribute(TDataStd_Name.GetID_s(), name)
        # pybind cannot convert single UTF-16 characters, so compare OCCT strings.
        if not name.Get().IsEqual(TCollection_ExtendedString(text, True)):
            return False
    return True


def test_failed_verification_leaves_the_target_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "bestehend.step"
    target.write_bytes(b"previous export")
    monkeypatch.setattr(
        export_api,
        "verify_step",
        lambda path, bodies: StepCheck(valid=True, solids=1, expected_solids=1, volume_error=1e-3),
    )
    with pytest.raises(KernelError) as failure:
        write_step(target, [("Halterung", _block())])
    assert failure.value.code == ErrorCode.VERIFY_FAILED
    assert target.read_bytes() == b"previous export"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["bestehend.step"]


def test_files_in_folders_with_umlauts(tmp_path: Path) -> None:
    folder = tmp_path / "Jörg Maß"
    folder.mkdir()
    write_step(folder / "teil.step", [("Gehäuse", _block())])
    written = write_stl(folder / "teil.stl", [_block()], 0.01)
    assert (folder / "teil.step").stat().st_size > 0
    assert written.triangles is not None and written.triangles > 1000


def test_stl_is_watertight_with_the_body_volume(tmp_path: Path) -> None:
    target = tmp_path / "teil.stl"
    written = write_stl(target, [_block(), _moved_box(150.0)], deflection=0.01)
    mesh = trimesh.load(target)
    assert written.bytes == target.stat().st_size == 84 + 50 * len(mesh.faces)
    assert mesh.is_watertight and mesh.is_winding_consistent
    expected = check_solid(_block_shape()).volume + 6000.0
    assert mesh.volume > 0 and mesh.volume == pytest.approx(expected, rel=2e-4)
    assert len(mesh.split(only_watertight=True)) == 2


def test_preflight_flags_open_bodies() -> None:
    assert check_body(_block()).problems == ()
    shell = _open_box()
    check = check_body(Body(shell))
    assert IssueCode.NOT_CLOSED in check.problems and check.blocking


def _open_box() -> object:
    """A solid whose shell misses one face of a box."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.TopoDS import TopoDS_Shell

    box = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    explorer = TopExp_Explorer(box, TopAbs_FACE)
    for _ in range(5):
        builder.Add(shell, explorer.Current())
        explorer.Next()
    return BRepBuilderAPI_MakeSolid(shell).Solid()


# --------------------------------------------------------------------------- commands


@pytest.fixture
def exported(session: Session) -> Iterator[Session]:
    with registered_types():
        scan = noisy_block()
        commit(
            session,
            scan_document(session, scan.vertices, scan.faces),
            feature("f1", "testBody", shape="block"),
            feature("f2", "testBody", shape="box"),
        )
        yield session


def test_file_methods_are_main_only() -> None:
    commands = load_commands()
    assert commands["export.step"].caller == "main"
    assert commands["export.stl"].caller == "main"
    assert commands["export.preflight"].caller == "renderer"


def test_preflight_command_names_the_owner(exported: Session, job: JobContext) -> None:
    result = export_preflight(job, PreflightParams(bodies=[]))
    assert result.exportable
    assert [(body.body, body.owner, body.blocking) for body in result.bodies] == [
        ("f1", "f1", False),
        ("f2", "f2", False),
    ]
    assert result.bodies[1].volume == pytest.approx(1000.0)


def test_step_command_writes_named_products(
    exported: Session, job: JobContext, tmp_path: Path
) -> None:
    target = tmp_path / "halterung.step"
    result = export_step(
        job,
        StepParams(path=str(target), bodies=["f1", "f2"], names=["Halterung 1", "Halterung 2"]),
    )
    assert result.file_name == "halterung.step"
    assert result.bodies == 2 and result.bytes == target.stat().st_size
    assert _xcaf_names_equal(target, ["Halterung 1", "Halterung 2"])


def test_step_command_checks_the_names(exported: Session, job: JobContext, tmp_path: Path) -> None:
    for names in (["nur einer"], ["", "zwei"]):
        with pytest.raises(KernelError) as failure:
            export_step(job, StepParams(path=str(tmp_path / "x.step"), bodies=[], names=names))
        assert failure.value.code == ErrorCode.INVALID_NAMES


def test_stl_command_and_blocked_bodies(
    exported: Session, job: JobContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = export_stl(job, StlParams(path=str(tmp_path / "teil.stl"), bodies=["f2"]))
    assert result.triangles == 12 and result.bodies == 1

    # The rebuild never lets an invalid solid through, so the check is replaced here.
    open_body = BodyCheck(
        valid=True, closed=False, solids=1, volume=1.0, area=6.0, max_tolerance=1e-7,
        problems=(IssueCode.NOT_CLOSED,),
    )  # fmt: skip
    monkeypatch.setattr(export_commands, "check_body", lambda body: open_body)
    report = export_preflight(job, PreflightParams(bodies=["f2"]))
    assert not report.exportable and report.bodies[0].problems == [IssueCode.NOT_CLOSED]
    target = tmp_path / "gesperrt.stl"
    with pytest.raises(KernelError) as failure:
        export_stl(job, StlParams(path=str(target), bodies=["f2"]))
    assert failure.value.code == ErrorCode.BLOCKED
    assert failure.value.params == {"body": "f2", "feature": "f2", "problem": "export.notClosed"}
    assert not target.exists()


def test_unknown_or_missing_bodies(session: Session, job: JobContext) -> None:
    with pytest.raises(KernelError) as failure:
        export_preflight(job, PreflightParams(bodies=[]))
    assert failure.value.code == ErrorCode.NO_BODY
    with registered_types():
        scan = noisy_block()
        commit(
            session,
            scan_document(session, scan.vertices, scan.faces),
            feature("f1", "testBody", shape="box"),
        )
        with pytest.raises(KernelError) as unknown:
            export_preflight(job, PreflightParams(bodies=["f5"]))
    assert unknown.value.code == ErrorCode.UNKNOWN_BODY
