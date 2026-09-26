"""Alignment to faces (3-2-1) from fit features, regions and stored face sets."""

from __future__ import annotations

from dataclasses import replace
from functools import cache

import numpy as np
import pytest

from m2c_kernel.alignment.api import evaluate
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
)
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.document.model import Alignment, AlignmentAdjust, Feature
from m2c_kernel.fitting.primitives import Cylinder
from m2c_kernel.geometry import matrix_array
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.alignment.conftest import (
    PosedScan,
    plane_face,
    pose_scan,
    surface_face,
    with_fit,
    with_regions,
)
from tests.synthetic.parts import SyntheticPart, tessellate_part

pytestmark = pytest.mark.occt

ROTATION_TOLERANCE_DEG = 20.0 / 3600.0
ORIGIN_TOLERANCE_MM = 0.01


def _faces_alignment(*refs: dict[str, str], adjust: AlignmentAdjust | None = None) -> Alignment:
    params: dict[str, object] = {"primary": refs[0], "secondary": refs[1], "tertiary": None}
    if len(refs) > 2:
        params["tertiary"] = refs[2]
    return Alignment(method="faces", params=params, adjust=adjust or AlignmentAdjust())  # type: ignore[arg-type]


def _feature(feature_id: str) -> dict[str, str]:
    return {"type": "feature", "feature": feature_id}


def _rotation_error_deg(rotation: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0))))


def _assert_design_frame(
    posed: PosedScan, matrix: tuple[float, ...], expected: np.ndarray | None = None
) -> None:
    transform = matrix_array(matrix)
    design_to_part = transform[:3, :3] @ posed.rotation
    target = np.eye(3) if expected is None else expected
    assert _rotation_error_deg(design_to_part @ target.T) < ROTATION_TOLERANCE_DEG
    design_origin = transform[:3, :3] @ posed.offset + transform[:3, 3]
    assert np.abs(design_origin).max() < ORIGIN_TOLERANCE_MM, design_origin


def _block_with_planes(session: Session, block: SyntheticPart, seed: int) -> PosedScan:
    posed = pose_scan(session, block, seed)
    posed = with_fit(session, posed, "f1", "plane", plane_face(block, (0, 0, -1), 0.0))
    posed = with_fit(session, posed, "f2", "plane", plane_face(block, (0, -1, 0), 0.0))
    posed = with_fit(session, posed, "f3", "plane", plane_face(block, (-1, 0, 0), 0.0))
    return with_fit(session, posed, "f4", "plane", plane_face(block, (0, 0, 1), 20.0))


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_three_fitted_planes(
    session: Session, job: JobContext, block: SyntheticPart, seed: int
) -> None:
    posed = _block_with_planes(session, block, seed)
    alignment = _faces_alignment(_feature("f1"), _feature("f2"), _feature("f3"))
    result = evaluate(posed.document, alignment, job)
    _assert_design_frame(posed, result.matrix)
    assert [fit.role for fit in result.inputs] == ["primary", "secondary", "tertiary"]
    assert all(
        fit.kind == "plane" and fit.rms is not None and fit.rms < 0.05 for fit in result.inputs
    )


def test_regions_and_stored_faces(session: Session, job: JobContext, block: SyntheticPart) -> None:
    posed = pose_scan(session, block, 24)
    posed = with_regions(
        session,
        posed,
        {
            "r1": ("plane", plane_face(block, (0, 0, -1), 0.0)),
            "r2": ("plane", plane_face(block, (0, -1, 0), 0.0)),
        },
    )
    side = np.nonzero(block.labels == plane_face(block, (-1, 0, 0), 0.0))[0].astype(np.uint32)
    alignment = _faces_alignment(
        {"type": "region", "region": "r1"},
        {"type": "region", "region": "r2"},
        {"type": "faces", "faces": session.blobs.put(side)},
    )
    result = evaluate(posed.document, alignment, job)
    _assert_design_frame(posed, result.matrix)
    assert result.inputs[2].kind == "plane"


def test_two_planes_put_the_free_coordinate_at_the_bounding_box_minimum(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = _block_with_planes(session, block, 25)
    result = evaluate(posed.document, _faces_alignment(_feature("f1"), _feature("f2")), job)
    transform = matrix_array(result.matrix)
    assert _rotation_error_deg(transform[:3, :3] @ posed.rotation) < ROTATION_TOLERANCE_DEG
    design_origin = transform[:3, :3] @ posed.offset + transform[:3, 3]
    # Y and Z come from the planes; X from the scan extent (spikes reach 0.3 mm).
    assert np.abs(design_origin[1:]).max() < ORIGIN_TOLERANCE_MM
    assert 0.0 <= design_origin[0] < 0.35


def test_adjust_turns_about_the_datum_origin(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = _block_with_planes(session, block, 26)
    refs = (_feature("f1"), _feature("f2"), _feature("f3"))
    flipped = evaluate(
        posed.document, _faces_alignment(*refs, adjust=AlignmentAdjust(flip_z=True)), job
    )
    _assert_design_frame(posed, flipped.matrix, expected=np.diag([1.0, -1.0, -1.0]))


@cache
def shaft_part() -> SyntheticPart:
    """A D20 x 60 shaft with a D12 x 20 journal on top and a flat at y = 8 (z 20..50)."""
    up = gp_Dir(0, 0, 1)
    shaft = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), up), 10.0, 60.0).Shape()
    journal = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 60), up), 6.0, 20.0).Shape()
    shape = BRepAlgoAPI_Fuse(shaft, journal).Shape()
    cutter = BRepPrimAPI_MakeBox(gp_Pnt(-15, 8, 20), 30.0, 10.0, 30.0).Shape()
    return tessellate_part(BRepAlgoAPI_Cut(shape, cutter).Shape(), 1.5)


def test_axis_and_end_face_on_a_shaft(session: Session, job: JobContext) -> None:
    shaft = shaft_part()
    main = next(
        index
        for index, surface in enumerate(shaft.surfaces)
        if isinstance(surface, Cylinder) and abs(surface.radius - 10.0) < 1e-6
    )
    posed = pose_scan(session, shaft, 31)
    posed = with_fit(session, posed, "f1", "cylinder", main)
    posed = with_fit(session, posed, "f2", "plane", plane_face(shaft, (0, 0, -1), 0.0))
    posed = with_fit(session, posed, "f3", "plane", plane_face(shaft, (0, 1, 0), 8.0))

    result = evaluate(posed.document, _faces_alignment(_feature("f1"), _feature("f2")), job)
    transform = matrix_array(result.matrix)
    design_to_part = transform[:3, :3] @ posed.rotation
    z_error = np.degrees(np.arccos(min(1.0, float(design_to_part[2] @ [0.0, 0.0, 1.0]))))
    assert z_error < ROTATION_TOLERANCE_DEG
    design_origin = transform[:3, :3] @ posed.offset + transform[:3, 3]
    assert np.abs(design_origin).max() < ORIGIN_TOLERANCE_MM

    # The flat fixes the rotation about the axis: Y points into the material (-y design).
    with_flat = evaluate(
        posed.document, _faces_alignment(_feature("f1"), _feature("f2"), _feature("f3")), job
    )
    _assert_design_frame(posed, with_flat.matrix, expected=np.diag([-1.0, -1.0, 1.0]))


def _error(
    session: Session, job: JobContext, posed: PosedScan, alignment: Alignment
) -> KernelError:
    with pytest.raises(KernelError) as raised:
        evaluate(posed.document, alignment, job)
    return raised.value


def test_invalid_inputs(session: Session, job: JobContext, block: SyntheticPart) -> None:
    posed = _block_with_planes(session, block, 27)
    posed = with_fit(session, posed, "f5", "sphere", surface_face(block, "sphere"))
    posed = with_regions(session, posed, {"r1": ("freeform", plane_face(block, (0, 0, 1), 20.0))})
    tiny = session.blobs.put(np.arange(50, dtype=np.uint32))
    cases: list[tuple[Alignment, str, str]] = [
        (_faces_alignment(_feature("f1"), _feature("f4")), ErrorCode.PARALLEL_INPUTS, "secondary"),
        (
            _faces_alignment(_feature("f1"), _feature("f2"), _feature("f4")),
            ErrorCode.NO_POINT,
            "tertiary",
        ),
        (_faces_alignment(_feature("f5"), _feature("f1")), ErrorCode.UNSUPPORTED_INPUT, "primary"),
        (_faces_alignment(_feature("f1"), _feature("f9")), ErrorCode.INPUT_NOT_FOUND, "secondary"),
        (
            _faces_alignment(_feature("f1"), {"type": "region", "region": "r1"}),
            ErrorCode.UNSUPPORTED_INPUT,
            "secondary",
        ),
        (
            _faces_alignment(_feature("f1"), {"type": "faces", "faces": tiny}),
            ErrorCode.TOO_FEW_FACES,
            "secondary",
        ),
    ]
    for alignment, code, role in cases:
        error = _error(session, job, posed, alignment)
        assert (error.code, error.params.get("input")) == (code, role)

    suppressed = replace(
        posed.document,
        features=tuple(
            replace(feature, suppressed=feature.id == "f2") for feature in posed.document.features
        ),
    )
    error = _error(
        session,
        job,
        replace(posed, document=suppressed),
        _faces_alignment(_feature("f1"), _feature("f2")),
    )
    assert error.code == ErrorCode.INPUT_NOT_FOUND

    malformed = Alignment(method="faces", params={"primary": {"type": "feature"}})
    assert _error(session, job, posed, malformed).code == ErrorCode.INVALID_PARAMS


def test_unknown_feature_types_are_unsupported(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = _block_with_planes(session, block, 28)
    sketch = Feature(id="f9", type="sketch", name=None, suppressed=False, params={})
    posed = replace(
        posed, document=replace(posed.document, features=(*posed.document.features, sketch))
    )
    error = _error(session, job, posed, _faces_alignment(_feature("f1"), _feature("f9")))
    assert (error.code, error.params.get("input")) == (ErrorCode.UNSUPPORTED_INPUT, "secondary")
