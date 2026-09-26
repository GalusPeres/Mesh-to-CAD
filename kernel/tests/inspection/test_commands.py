"""The inspection protocol commands on a session with a scan, a body and fits."""

from __future__ import annotations

import time
from collections.abc import Iterator

import numpy as np
import pytest

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.inspection import ErrorCode
from m2c_kernel.commands.inspection import (
    BodyFaceItem,
    DeviationParams,
    DeviationResult,
    FeatureItem,
    MeasureParams,
    OriginPartItem,
    PreviewDeviationParams,
    inspection_deviation,
    inspection_measure,
    inspection_preview_deviation,
)
from m2c_kernel.document.model import Document
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import load_commands
from m2c_kernel.protocol.wire import to_wire
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.inspection.scene import (
    commit,
    face_set,
    feature,
    noisy_block,
    registered_types,
    scan_document,
)

pytestmark = pytest.mark.occt

TOP, BOTTOM, HOLE = 4, 15, 14


@pytest.fixture(autouse=True)
def types() -> Iterator[None]:
    with registered_types():
        yield


@pytest.fixture
def document(session: Session) -> Document:
    scan = noisy_block()
    base = scan_document(session, scan.vertices, scan.faces)
    faces = {label: np.flatnonzero(scan.labels == label) for label in (TOP, BOTTOM, HOLE)}
    return commit(
        session,
        base,
        feature("f1", "testBody", shape="block"),
        feature("f2", "testFit", faces=face_set(session, faces[TOP]), kind="plane"),
        feature("f3", "testFit", faces=face_set(session, faces[BOTTOM]), kind="plane"),
        feature("f4", "testFit", faces=face_set(session, faces[HOLE]), kind="cylinder"),
    )


def test_methods_are_registered_as_specified() -> None:
    commands = load_commands()
    deviation = commands["inspection.deviation"]
    assert deviation.lane and deviation.exclusive and deviation.caller == "renderer"
    assert commands["inspection.previewDeviation"].lane
    assert commands["inspection.measure"].lane


def test_deviation_map_of_the_whole_scan(
    session: Session, job: JobContext, document: Document
) -> None:
    result = inspection_deviation(job, DeviationParams(bodies=[], max_distance=2.0))
    assert result.revision == document.revision
    assert document.scan is not None and result.scan_key == document.scan.key
    assert result.bodies == ["f1"]
    assert result.values.dtype == np.float32 and len(result.values) == document.scan.vertex_count
    assert len(result.face_values) == document.scan.face_count
    assert result.stats.passed and result.stats.count == len(result.values)
    # The per-vertex arrays travel as binary buffers, the statistics as JSON.
    json, buffers = to_wire(result, DeviationResult)
    assert [len(buffer) for buffer in buffers] == [len(result.values), len(result.face_values)]
    assert json["stats"]["within"] == pytest.approx(result.stats.within)


def test_deviation_rejects_missing_bodies(session: Session, job: JobContext) -> None:
    scan = noisy_block()
    commit(session, scan_document(session, scan.vertices, scan.faces))
    with pytest.raises(KernelError) as missing:
        inspection_deviation(job, DeviationParams(bodies=[], max_distance=2.0))
    assert missing.value.code == ErrorCode.NO_BODY
    commit(session, session.document, feature("f1", "testBody", shape="box"))
    with pytest.raises(KernelError) as unknown:
        inspection_deviation(job, DeviationParams(bodies=["f7"], max_distance=2.0))
    assert unknown.value.code == ErrorCode.UNKNOWN_BODY


def test_deviation_needs_a_scan(session: Session, job: JobContext) -> None:
    with pytest.raises(KernelError) as failure:
        inspection_deviation(job, DeviationParams(bodies=[], max_distance=2.0))
    assert failure.value.code == DocumentError.NO_SCAN


def test_preview_deviation_uses_the_cached_result(
    session: Session, job: JobContext, document: Document
) -> None:
    key = session.built(job).result.result_keys["f1"]
    start = time.perf_counter()
    result = inspection_preview_deviation(job, PreviewDeviationParams(result_key=key))
    assert time.perf_counter() - start < 1.0
    assert result.bodies == ["f1"]
    assert result.points == 50_000 and result.stats.passed
    with pytest.raises(KernelError) as failure:
        inspection_preview_deviation(job, PreviewDeviationParams(result_key="gone"))
    assert failure.value.code == ErrorCode.NO_PREVIEW


def test_measure_between_fits_carries_uncertainties(
    session: Session, job: JobContext, document: Document
) -> None:
    result = inspection_measure(
        job, MeasureParams(a=FeatureItem(feature="f2"), b=FeatureItem(feature="f3"))
    )
    assert result.kind_a == result.kind_b == "plane"
    assert result.distance is not None and result.distance.value == pytest.approx(20.0, abs=0.003)
    assert result.distance.uncertainty is not None and 0 < result.distance.uncertainty < 0.002
    assert result.parallel and result.distance_kind == "parallel"
    again = inspection_measure(
        job, MeasureParams(a=FeatureItem(feature="f2"), b=FeatureItem(feature="f3"))
    )
    assert again == result, "seeded: the same request gives the same numbers"
    hole = inspection_measure(job, MeasureParams(a=FeatureItem(feature="f4")))
    assert hole.diameter_a is not None and hole.diameter_a.value == pytest.approx(16.0, abs=0.02)
    assert hole.diameter_a.uncertainty is not None


def test_measure_body_faces_and_origin_items_exactly(
    session: Session, job: JobContext, document: Document
) -> None:
    faces = [
        inspection_measure(
            job,
            MeasureParams(a=BodyFaceItem(body="f1", face=index), b=OriginPartItem(item="XY")),
        )
        for index in range(16)
    ]
    heights = sorted(
        round(m.distance.value, 9) for m in faces if m.parallel and m.distance is not None
    )
    # Bottom, top of the block, top of the boss: exact values, no uncertainty.
    assert heights == [0.0, 20.0, 35.0]
    assert all(m.distance is None or m.distance.uncertainty is None for m in faces)
    assert sum(m.kind_a == "axis" for m in faces) == 8  # 4 fillets, boss, hole, cone, torus


@pytest.mark.parametrize(
    ("item", "code"),
    [
        (FeatureItem(feature="f99"), ErrorCode.UNKNOWN_ITEM),
        (FeatureItem(feature="f1"), ErrorCode.NOT_MEASURABLE),
        (BodyFaceItem(body="f1", face=16), ErrorCode.UNKNOWN_ITEM),
        (BodyFaceItem(body="f9", face=0), ErrorCode.UNKNOWN_ITEM),
    ],
)
def test_measure_reports_unusable_items(
    session: Session, job: JobContext, document: Document, item: object, code: ErrorCode
) -> None:
    with pytest.raises(KernelError) as failure:
        inspection_measure(job, MeasureParams(a=item))  # type: ignore[arg-type]
    assert failure.value.code == code
