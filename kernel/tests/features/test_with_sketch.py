"""Solid features on a real sketch fitted to a noisy scan, through `doc.apply`.

The scan is the synthetic test plate (100 x 60 x 10 with a chamfer, three corner
fillets, a notch and two holes, 0.02 mm noise). The sketch package fits the
outline at mid height; extruding it by the plate thickness must give the plate
back, and a fillet on a hole edge must survive a new extrusion height.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from OCP.GeomAbs import GeomAbs_Cylinder

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import BRepAdaptor_Surface, TopoDS
from m2c_kernel.cad.tags import faces_of
from m2c_kernel.commands.doc import ApplyParams, PreviewParams, doc_apply, doc_preview
from m2c_kernel.commands.sketch import AutoFitParams, sketch_auto_fit
from m2c_kernel.document.model import Document, Scan, ScanSource
from m2c_kernel.document.ops import AddFeature, NewFeature, UpdateFeature
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.wire import RawObject, to_json
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from m2c_kernel.sketch.params import SketchParams
from tests.sketch.conftest import PLATE_SPEC, noisy_plate
from tests.synthetic.parts import build_test_plate
from tests.timing import budget

pytestmark = pytest.mark.occt

HOLE_RADIUS = 6.0
HOLE_CENTRES = [(-25.0, -5.0), (25.0, -5.0)]


def _plate_document(session: Session) -> Document:
    scan = noisy_plate(0.02)
    origin = np.round(scan.vertices.mean(axis=0), 1)
    return replace(
        Document.empty(),
        scan=Scan(
            key="scan:plate",
            source=ScanSource("plate.stl", "0", "mm"),
            vertices=session.blobs.put((scan.vertices - origin).astype(np.float32)),
            faces=session.blobs.put(scan.faces.astype(np.uint32)),
            synthetic=None,
            vertex_count=len(scan.vertices),
            face_count=len(scan.faces),
            origin=(float(origin[0]), float(origin[1]), float(origin[2])),
            noise=0.02,
        ),
    )


def _apply(session: Session, job: JobContext, *ops: Any) -> None:
    params = ApplyParams(base_revision=session.document.revision, ops=list(ops), label="test")
    doc_apply(job, params)


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    _apply(session, job, AddFeature(feature=NewFeature(type=type_id, params=RawObject(params))))
    return session.document.features[-1].id


def _body(session: Session, job: JobContext, body_id: str) -> Body:
    return session.built(job).result.bodies[body_id]


def _hole_sides(body: Body) -> dict[str, tuple[float, float]]:
    """Tag and axis position (x, y) of the side faces of the two full holes (radius 6)."""
    faces = faces_of(body.shape)
    holes = {}
    for index, tag in enumerate(body.face_tags):
        surface = BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(index + 1)))
        if surface.GetType() == GeomAbs_Cylinder and surface.Cylinder().Radius() < 7.0:
            axis = surface.Cylinder().Location()
            holes[tag] = (axis.X(), axis.Y())
    return holes


@pytest.fixture
def plate(session: Session, job: JobContext) -> tuple[Session, str, str]:
    """Session with the plate scan, its fitted sketch and a 10 mm extrusion."""
    session.commit(_plate_document(session), "import", job)
    fitted = sketch_auto_fit(job, AutoFitParams(sketch=SketchParams(section=PLATE_SPEC)))
    sketch = _add(session, job, "sketch", to_json(fitted.sketch, SketchParams))
    extent = {"type": "distance", "forward": 10.0}
    extrude = _add(session, job, "extrude", {"sketch": sketch, "extent": extent})
    return session, sketch, extrude


def test_extruded_sketch_gives_the_plate_back(
    plate: tuple[Session, str, str], job: JobContext
) -> None:
    session, _sketch, extrude = plate
    body = _body(session, job, extrude)
    true_volume = check_solid(build_test_plate()).volume
    assert check_solid(body.shape).is_usable
    # The fitted outline snaps to the design values, so the volume is exact up to rounding.
    assert check_solid(body.shape).volume == pytest.approx(true_volume, rel=1e-5)
    sides = [tag for tag in body.face_tags if tag.startswith(f"{extrude}:side:")]
    assert len(sides) == len(set(sides)), "every side face is named after its own entity"
    holes = sorted(_hole_sides(body).values())
    assert np.allclose(holes, HOLE_CENTRES, atol=1e-6)


def test_fillet_on_a_hole_edge_survives_a_new_height(
    plate: tuple[Session, str, str], job: JobContext
) -> None:
    session, sketch, extrude = plate
    body = _body(session, job, extrude)
    hole, (x, y) = next(iter(_hole_sides(body).items()))
    point = [x + HOLE_RADIUS, y, 10.0]
    edge = {"faces": [f"{extrude}:cap:end", hole], "point": point}
    radius = 1.0
    params = {"targetBody": extrude, "edges": [edge], "size": radius}
    fillet = _add(session, job, "fillet", params)
    assert session.snapshot("current", job).status.features[fillet].state == "ok"

    # Pappus: the removed corner area r^2 (1 - pi/4) turns about the hole axis at the
    # radius of its centroid, R + r (10 - 3 pi) / (12 - 3 pi).
    corner = radius**2 * (1 - math.pi / 4)
    centroid = HOLE_RADIUS + radius * (10 - 3 * math.pi) / (12 - 3 * math.pi)
    removed = corner * 2 * math.pi * centroid
    before = check_solid(body.shape).volume
    after = check_solid(_body(session, job, extrude).shape).volume
    assert before - after == pytest.approx(removed, rel=1e-6)

    extent = {"type": "distance", "forward": 12.0}
    changed = {"sketch": sketch, "extent": extent}
    _apply(session, job, UpdateFeature(id=extrude, params=RawObject(changed)))
    status = session.snapshot("current", job).status.features[fillet]
    assert status.state == "ok", status
    taller = check_solid(_body(session, job, extrude).shape).volume
    assert taller - after == pytest.approx(before / 10 * 2, rel=1e-6)


def test_preview_of_a_real_extrusion_is_fast(
    plate: tuple[Session, str, str], job: JobContext
) -> None:
    import time

    session, sketch, extrude = plate
    params = {"sketch": sketch, "extent": {"type": "distance", "forward": 11.0}}
    started = time.perf_counter()
    preview = doc_preview(
        job,
        PreviewParams(
            base_revision=session.document.revision,
            ops=[UpdateFeature(id=extrude, params=RawObject(params))],
        ),
    )
    elapsed = time.perf_counter() - started
    assert preview.status is not None and preview.status.state == "ok"
    assert elapsed < budget(0.5)


def test_preview_items_carry_the_result_key_for_the_deviation(
    plate: tuple[Session, str, str], job: JobContext
) -> None:
    """The solid panels read the result key from the preview's body item keys
    (`body:<resultKey>:…`) and ask `inspection.previewDeviation` with it."""
    from m2c_kernel.commands.inspection import (
        PreviewDeviationParams,
        inspection_preview_deviation,
    )

    session, sketch, extrude = plate
    params = {"sketch": sketch, "extent": {"type": "distance", "forward": 10.0}}
    preview = doc_preview(
        job,
        PreviewParams(
            base_revision=session.document.revision,
            ops=[UpdateFeature(id=extrude, params=RawObject(params))],
        ),
    )
    keys = [item.key for item in preview.items if item.owner == preview.feature_id]
    assert keys and all(key.startswith(("body:r:", "src:r:")) for key in keys)
    result_key = keys[0].split(":")[1] + ":" + keys[0].split(":")[2]

    deviation = inspection_preview_deviation(job, PreviewDeviationParams(result_key=result_key))
    assert deviation.bodies == [extrude]
    assert deviation.points > 1000
    assert deviation.stats.passed
