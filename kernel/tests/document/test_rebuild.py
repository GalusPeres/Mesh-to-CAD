"""Rebuild engine behaviour, checked with test-only feature types."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

import pytest

from m2c_kernel.document.model import Document, DocumentSettings, Feature
from m2c_kernel.document.rebuild import EvalContext, rebuild
from m2c_kernel.document.results import Body, BodyUpdate, FeatureOutput, Issue
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import FeatureTypeSpec, ReadSet, Refs, temporary_feature_type
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session

pytestmark = pytest.mark.occt

evaluations: list[str] = []


@dataclass(frozen=True, kw_only=True)
class BoxParams:
    size: float
    fail: bool = False


@dataclass(frozen=True, kw_only=True)
class ScaleParams:
    source: str
    factor: float


def _box(ctx: EvalContext, params: BoxParams) -> FeatureOutput:
    from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox

    evaluations.append(ctx.feature_id)
    if params.fail:
        raise KernelError("cad.invalidResult", {"reason": "requested"})
    shape = BRepPrimAPI_MakeBox(params.size, params.size, params.size).Shape()
    return FeatureOutput(bodies=BodyUpdate(changed={ctx.feature_id: Body(shape)}))


def _scale(ctx: EvalContext, params: ScaleParams) -> FeatureOutput:
    from m2c_kernel.cad.occ_compat import BRepBuilderAPI_Transform, gp_Trsf

    evaluations.append(ctx.feature_id)
    transform = gp_Trsf()
    transform.SetScaleFactor(params.factor)
    shape = BRepBuilderAPI_Transform(ctx.body(params.source).shape, transform, True).Shape()
    issues = (Issue("cad.highTolerance"),) if params.factor > 2 else ()
    return FeatureOutput(bodies=BodyUpdate(changed={params.source: Body(shape)}), issues=issues)


def _tolerance_reader(ctx: EvalContext, params: BoxParams) -> FeatureOutput:
    evaluations.append(ctx.feature_id)
    return FeatureOutput(stats={"tolerance": ctx.settings.tolerance})


BOX = FeatureTypeSpec(
    type_id="testBox",
    params_type=BoxParams,
    input_type=BoxParams,
    reads=ReadSet(),
    references=lambda params: Refs(),
    evaluate=_box,
    store=lambda value, blobs: value,
    module=__name__,
)
SCALE = FeatureTypeSpec(
    type_id="testScale",
    params_type=ScaleParams,
    input_type=ScaleParams,
    reads=ReadSet(),
    references=lambda params: Refs(bodies=feature_refs(params.source)),
    evaluate=_scale,
    store=lambda value, blobs: value,
    module=__name__,
)
TOLERANCE = replace(
    BOX, type_id="testTolerance", reads=ReadSet(settings=("tolerance",)), evaluate=_tolerance_reader
)


@pytest.fixture(autouse=True)
def test_types() -> Iterator[None]:
    evaluations.clear()
    with (
        temporary_feature_type(BOX),
        temporary_feature_type(SCALE),
        temporary_feature_type(TOLERANCE),
    ):
        yield


def _document(*features: Feature, tolerance: float = 0.1) -> Document:
    return replace(
        Document.empty(), features=features, settings=DocumentSettings(tolerance=tolerance)
    )


def _feature(feature_id: str, type_id: str, **params: object) -> Feature:
    return Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=dict(params))


def test_bodies_and_statuses(session: Session, job: JobContext) -> None:
    document = _document(
        _feature("f1", "testBox", size=10.0),
        _feature("f2", "testScale", source="f1", factor=3.0),
    )
    result = rebuild(document, session.environment(), job)
    assert result.statuses["f1"].state == "ok"
    assert result.statuses["f2"].state == "warning"
    assert result.body_owner == {"f1": "f2"}
    assert result.body_checks["f1"].volume == pytest.approx(27_000.0)


def test_unchanged_features_are_cache_hits(session: Session, job: JobContext) -> None:
    box = _feature("f1", "testBox", size=10.0)
    scale = _feature("f2", "testScale", source="f1", factor=2.0)
    env = session.environment()
    rebuild(_document(box, scale), env, job)
    evaluations.clear()

    changed = replace(scale, params={"source": "f1", "factor": 1.5})
    rebuild(_document(box, changed), env, job)
    assert evaluations == ["f2"]


def test_a_failed_feature_skips_its_dependents_only(session: Session, job: JobContext) -> None:
    document = _document(
        _feature("f1", "testBox", size=10.0, fail=True),
        _feature("f2", "testScale", source="f1", factor=2.0),
        _feature("f3", "testBox", size=5.0),
    )
    result = rebuild(document, session.environment(), job)
    assert result.statuses["f1"].state == "error"
    assert result.statuses["f1"].error is not None
    assert result.statuses["f1"].error.code == "cad.invalidResult"
    assert result.statuses["f2"].state == "skipped"
    assert result.statuses["f3"].state == "ok"


def test_suppressed_features_produce_nothing(session: Session, job: JobContext) -> None:
    box = replace(_feature("f1", "testBox", size=10.0), suppressed=True)
    result = rebuild(_document(box), session.environment(), job)
    assert result.statuses["f1"].state == "suppressed"
    assert not result.bodies


def test_a_settings_change_reevaluates_only_features_that_read_it(
    session: Session, job: JobContext
) -> None:
    features = (_feature("f1", "testBox", size=10.0), _feature("f2", "testTolerance", size=1.0))
    env = session.environment()
    rebuild(_document(*features, tolerance=0.1), env, job)
    evaluations.clear()

    result = rebuild(_document(*features, tolerance=0.2), env, job)
    assert evaluations == ["f2"]
    assert result.statuses["f2"].stats["tolerance"] == 0.2


def test_invalid_stored_parameters_fail_that_feature(session: Session, job: JobContext) -> None:
    result = rebuild(_document(_feature("f1", "testBox", size="big")), session.environment(), job)
    assert result.statuses["f1"].state == "error"
    assert result.statuses["f1"].error is not None
    assert result.statuses["f1"].error.code == "kernel.invalidParams"
