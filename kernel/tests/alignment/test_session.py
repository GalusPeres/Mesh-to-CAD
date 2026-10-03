"""The alignment in the session: preview command, commit, rebuild and reference inputs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

import numpy as np
import pytest

from m2c_kernel.alignment.api import evaluate
from m2c_kernel.alignment.params import FeatureInput
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.commands.alignment import (
    AlignmentPreviewParams,
    SelectionInput,
    alignment_preview,
)
from m2c_kernel.document.model import Alignment, AlignmentAdjust, Feature
from m2c_kernel.document.ops import SetAlignment, apply_ops
from m2c_kernel.document.rebuild import EvalContext, rebuild
from m2c_kernel.document.results import Construction, FeatureOutput
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import (
    FeatureTypeSpec,
    ReadSet,
    Refs,
    load_feature_types,
    temporary_feature_type,
)
from m2c_kernel.fitting.api import Plane, fit_primitive
from m2c_kernel.geometry import matrix_array, unit, vec3
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, JsonValue
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.alignment.conftest import plane_face, pose_scan, with_fit
from tests.synthetic.parts import SyntheticPart

pytestmark = pytest.mark.occt

evaluated: list[str] = []
received: dict[str, ProbeFitParams] = {}


@dataclass(frozen=True, kw_only=True)
class ProbeFitParams:
    faces: BlobRef
    kind: str
    source_region: str | None = None
    robust: bool = False
    fixed: dict[str, float] | None = None
    relation: JsonValue = None
    snap: bool = True
    rejected_snaps: list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class MidPlaneParams:
    first: str
    second: str


@dataclass(frozen=True, kw_only=True)
class SketchParams:
    offset: float


@dataclass(frozen=True, kw_only=True)
class ExtrudeParams:
    sketch: str


def _probe_fit(ctx: EvalContext, params: ProbeFitParams) -> FeatureOutput:
    evaluated.append(ctx.feature_id)
    received[ctx.feature_id] = params
    faces = ctx.face_set(params.faces)
    fit = fit_primitive(
        "plane", ctx.mesh.face_centroids[faces], ctx.mesh.face_normals[faces], ctx.rng
    )
    return FeatureOutput(construction=Construction(primitive=fit.primitive))


def _mid_plane(ctx: EvalContext, params: MidPlaneParams) -> FeatureOutput:
    evaluated.append(ctx.feature_id)
    first = ctx.construction(params.first).primitive
    second = ctx.construction(params.second).primitive
    assert isinstance(first, Plane) and isinstance(second, Plane)
    normal = unit(np.asarray(first.normal) - np.asarray(second.normal))
    origin = (np.asarray(first.origin) + np.asarray(second.origin)) / 2
    return FeatureOutput(
        construction=Construction(primitive=Plane(origin=vec3(origin), normal=vec3(normal)))
    )


def _sketch(ctx: EvalContext, params: SketchParams) -> FeatureOutput:
    evaluated.append(ctx.feature_id)
    return FeatureOutput(stats={"offset": params.offset})


def _extrude(ctx: EvalContext, params: ExtrudeParams) -> FeatureOutput:
    evaluated.append(ctx.feature_id)
    ctx.output(params.sketch)
    return FeatureOutput()


FIT = FeatureTypeSpec(
    type_id="fit",
    params_type=ProbeFitParams,
    input_type=ProbeFitParams,
    reads=ReadSet(mesh=True),
    references=lambda params: Refs(),
    evaluate=_probe_fit,
    store=lambda value, blobs: value,
    module=__name__,
)
REFERENCE = FeatureTypeSpec(
    type_id="reference",
    params_type=MidPlaneParams,
    input_type=MidPlaneParams,
    reads=ReadSet(alignment=True),
    references=lambda params: Refs(features=feature_refs(params.first, params.second)),
    evaluate=_mid_plane,
    store=lambda value, blobs: value,
    module=__name__,
)
SKETCH = FeatureTypeSpec(
    type_id="probeSketch",
    params_type=SketchParams,
    input_type=SketchParams,
    reads=ReadSet(),
    references=lambda params: Refs(),
    evaluate=_sketch,
    store=lambda value, blobs: value,
    module=__name__,
)
EXTRUDE = FeatureTypeSpec(
    type_id="probeExtrude",
    params_type=ExtrudeParams,
    input_type=ExtrudeParams,
    reads=ReadSet(),
    references=lambda params: Refs(features=feature_refs(params.sketch)),
    evaluate=_extrude,
    store=lambda value, blobs: value,
    module=__name__,
)


@pytest.fixture(autouse=True)
def probe_types() -> Iterator[None]:
    """Stand-ins for fits and references; the real modules are loaded first, then replaced."""
    load_feature_types()
    evaluated.clear()
    received.clear()
    with (
        temporary_feature_type(FIT),
        temporary_feature_type(REFERENCE),
        temporary_feature_type(SKETCH),
        temporary_feature_type(EXTRUDE),
    ):
        yield


def _feature(feature_id: str, type_id: str, params: dict[str, JsonValue]) -> Feature:
    return Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=params)


def test_preview_stores_the_selection_and_the_commit_uses_it(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = pose_scan(session, block, 41)
    posed = with_fit(session, posed, "f1", "plane", plane_face(block, (0, 0, -1), 0.0))
    posed = with_fit(session, posed, "f2", "plane", plane_face(block, (0, -1, 0), 0.0))
    session.commit(replace(posed.document, next_id=3), "setup", job)
    side = np.nonzero(block.labels == plane_face(block, (-1, 0, 0), 0.0))[0].astype(np.uint32)

    preview = alignment_preview(
        job,
        AlignmentPreviewParams(
            method="faces",
            primary=FeatureInput(feature="f1"),
            secondary=FeatureInput(feature="f2"),
            tertiary=SelectionInput(faces=side),
            adjust=AlignmentAdjust(rotate_z90=1),
        ),
    )
    assert isinstance(preview.params, dict)
    tertiary = preview.params["tertiary"]
    assert isinstance(tertiary, dict) and tertiary["type"] == "faces"
    assert str(tertiary["faces"]).startswith("blob:")
    assert [fit.role for fit in preview.inputs] == ["primary", "secondary", "tertiary"]

    evaluated.clear()
    op = SetAlignment(method="faces", params=preview.params, adjust=AlignmentAdjust(rotate_z90=1))
    applied = apply_ops(session.document, [op], session.feature_types, session.blobs)
    snapshot = session.commit(applied.document, "alignment", job)
    assert snapshot.scene.scan is not None
    np.testing.assert_allclose(snapshot.scene.scan.transform, preview.matrix, atol=1e-12)
    # Both fits read the scan, so the new alignment evaluates them again.
    assert evaluated == ["f1", "f2"]
    transform = matrix_array(preview.matrix)
    design_to_part = transform[:3, :3] @ posed.rotation
    np.testing.assert_allclose(design_to_part, [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-4)


def test_auto_preview_reports_the_remaining_tilt(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = pose_scan(session, block, 42)
    session.commit(posed.document, "import", job)
    preview = alignment_preview(job, AlignmentPreviewParams(method="auto"))
    assert preview.params is None
    assert preview.largest_plane is not None
    assert preview.largest_plane.plane == "XY"
    assert preview.largest_plane.tilt_deg < 0.01
    assert preview.issues == []


def test_new_alignment_rebuilds_only_scan_readers(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    posed = pose_scan(session, block, 43)
    posed = with_fit(session, posed, "f1", "plane", plane_face(block, (0, 0, -1), 0.0))
    document = replace(
        posed.document,
        features=(
            *posed.document.features,
            _feature("f2", "probeSketch", {"offset": 5.0}),
            _feature("f3", "probeExtrude", {"sketch": "f2"}),
        ),
    )
    environment = session.environment()
    rebuild(document, environment, job)
    assert evaluated == ["f1", "f2", "f3"]

    evaluated.clear()
    aligned = replace(document, alignment=Alignment(method="auto"))
    result = rebuild(aligned, environment, job)
    assert evaluated == ["f1"]
    assert all(result.statuses[feature_id].state == "ok" for feature_id in ("f1", "f2", "f3"))


def test_reference_input_is_evaluated_in_scan_coordinates(
    session: Session, job: JobContext, block: SyntheticPart
) -> None:
    """A mid-plane of the two long sides becomes the XZ plane: the part is centred in Y."""
    posed = pose_scan(session, block, 44)
    posed = with_fit(session, posed, "f1", "plane", plane_face(block, (0, 0, -1), 0.0))
    posed = with_fit(session, posed, "f2", "plane", plane_face(block, (0, -1, 0), 0.0))
    posed = with_fit(session, posed, "f3", "plane", plane_face(block, (0, 1, 0), 70.0))
    posed = with_fit(session, posed, "f4", "plane", plane_face(block, (-1, 0, 0), 0.0))
    relation: JsonValue = {"type": "parallel", "to": "Z"}
    fits = [
        replace(feature, params={**_params(feature), "relation": relation})
        for feature in posed.document.features
    ]
    mid = _feature("f5", "reference", {"first": "f2", "second": "f3"})
    document = replace(posed.document, features=(*fits, mid))
    refs: dict[str, JsonValue] = {
        "primary": {"type": "feature", "feature": "f1"},
        "secondary": {"type": "feature", "feature": "f5"},
        "tertiary": {"type": "feature", "feature": "f4"},
    }
    alignment = Alignment(method="faces", params=refs)
    result = evaluate(document, alignment, job)
    assert result.inputs[1].kind == "plane"
    # The mid-plane chain was evaluated on fits without their part-coordinate relation.
    assert all(received[fit].relation is None for fit in ("f2", "f3"))
    transform = matrix_array(result.matrix)
    design_centre = posed.design_to_scan(np.array([[0.0, 35.0, 0.0]]))[0]
    part_centre = transform[:3, :3] @ design_centre + transform[:3, 3]
    assert abs(part_centre[1]) < 0.01
    assert abs(part_centre[0]) < 0.01 and abs(part_centre[2]) < 0.01
    design_to_part = transform[:3, :3] @ posed.rotation
    assert abs(abs(design_to_part[1, 1]) - 1.0) < 1e-6

    uses_standard_plane = _feature("f6", "reference", {"first": "f2", "second": "XY"})
    document = replace(document, features=(*document.features, uses_standard_plane))
    bad = replace(alignment, params={**refs, "secondary": {"type": "feature", "feature": "f6"}})
    with pytest.raises(KernelError) as raised:
        evaluate(document, bad, job)
    assert raised.value.code == ErrorCode.UNSUPPORTED_INPUT


def _params(feature: Feature) -> dict[str, JsonValue]:
    assert isinstance(feature.params, dict)
    return feature.params
