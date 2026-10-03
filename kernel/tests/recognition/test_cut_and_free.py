"""Outlines that are no whole template: a button cut by the part's outline and a free
pocket, recognised as lines and arcs and built; and the direction pad's design intent."""

from __future__ import annotations

from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Common,
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepBuilderAPI_Transform,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    TopoDS_Shape,
    gp_Ax1,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
    gp_Trsf,
)
from m2c_kernel.commands.doc import ApplyParams, doc_apply
from m2c_kernel.commands.recognize import (
    BuildParams,
    RecognizeParams,
    recognize_build,
    recognize_run,
)
from m2c_kernel.document.model import Document, Scan, ScanSource
from m2c_kernel.document.ops import AddFeature, NewFeature
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.recognition.api import Feature, Recognition, recognize
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

NOISE = 0.02


def _cylinder(x: float, y: float, z: float, diameter: float, height: float) -> TopoDS_Shape:
    axis = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, diameter / 2.0, height).Shape()


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> TopoDS_Shape:
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), x1 - x0, y1 - y0, z1 - z0).Shape()


def edge_part() -> TopoDS_Shape:
    """80 x 50 x 6 plate: a D8 x 2 button at (78, 25) cut by the end face at x = 80, a
    whole D8 x 2 button at (60, 25), and a 2 mm deep keyhole pocket: a D10 hole at
    (25, 25) with a 4 mm wide tail to x = 40."""
    plate = _box(0, 0, 0, 80, 50, 6)
    cut_button = BRepAlgoAPI_Common(_cylinder(78, 25, 6, 8, 2), _box(0, 0, 6, 80, 50, 8)).Shape()
    shape = BRepAlgoAPI_Fuse(plate, cut_button).Shape()
    shape = BRepAlgoAPI_Fuse(shape, _cylinder(60, 25, 6, 8, 2)).Shape()
    keyhole = BRepAlgoAPI_Fuse(_cylinder(25, 25, 4, 10, 3), _box(25, 23, 4, 40, 27, 7)).Shape()
    return BRepAlgoAPI_Cut(shape, keyhole).Shape()


def _scan(shape: TopoDS_Shape, seed: int) -> tuple[np.ndarray, np.ndarray]:
    part = tessellate_part(shape, max_edge=0.8)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, NOISE, np.random.default_rng(seed))
    return noisy, part.faces


@cache
def edge_recognition() -> Recognition:
    vertices, faces = _scan(edge_part(), 11)
    return recognize(vertices, faces, NOISE)


def _top(recognition: Recognition, height: float = 6.0) -> list[Feature]:
    top = next(
        i
        for i, plane in enumerate(recognition.planes)
        if plane.normal[2] > 0.99 and abs(plane.origin[2] - height) < 0.1
    )
    return [feature for feature in recognition.features if feature.plane == top]


def test_a_button_cut_by_the_outline_is_a_cut_circle_measured_like_its_twin() -> None:
    features = _top(edge_recognition())
    cut = next(f for f in features if f.outline.kind == "cutCircle")
    whole = next(f for f in features if f.outline.kind == "circle" and f.relief.kind == "boss")
    p = cut.outline.named()
    assert p["radius"] == pytest.approx(4.0, abs=0.1)
    # The cut lies on the end face, 2 mm beyond the centre, its normal along +x.
    assert p["cut"] == pytest.approx(2.0, abs=0.1)
    assert np.cos(p["angle"]) == pytest.approx(1.0, abs=1e-3)
    assert p["radius"] == pytest.approx(whole.outline.named()["radius"], abs=0.05)
    assert cut.relief.height == pytest.approx(2.0, abs=0.1)
    arc, line = cut.outline.chain.edges
    assert arc.is_arc and not line.is_arc


def test_a_free_pocket_is_one_arc_and_three_lines() -> None:
    pocket = next(f for f in _top(edge_recognition()) if f.relief.kind == "pocket")
    assert pocket.outline.kind == "profile"
    assert pocket.relief.height == pytest.approx(2.0, abs=0.1)
    edges = pocket.outline.chain.edges
    assert sorted(edge.is_arc for edge in edges) == [False, False, False, True]
    arc = next(edge for edge in edges if edge.is_arc)
    assert arc.radius == pytest.approx(5.0, abs=0.1)


def _scan_document(session: Session, vertices: np.ndarray, faces: np.ndarray) -> Document:
    return replace(
        Document.empty(),
        scan=Scan(
            key="scan:edge",
            source=ScanSource("edge.stl", "0", "mm"),
            vertices=session.blobs.put(vertices.astype(np.float32)),
            faces=session.blobs.put(faces.astype(np.uint32)),
            synthetic=None,
            vertex_count=len(vertices),
            face_count=len(faces),
            origin=(0.0, 0.0, 0.0),
            noise=NOISE,
        ),
    )


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    op = AddFeature(feature=NewFeature(type=type_id, params=RawObject(params)))
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=[op], label="t"))
    return session.document.features[-1].id


def test_cut_and_free_outlines_build_the_part(session: Session, job: JobContext) -> None:
    vertices, faces = _scan(edge_part(), 13)
    session.commit(_scan_document(session, vertices, faces), "import", job)
    corners = [(0.0, 0.0), (80.0, 0.0), (80.0, 50.0), (0.0, 50.0)]
    plate_sketch = _add(
        session,
        job,
        "sketch",
        {
            "section": {"type": "planar", "plane": {"type": "standard", "plane": "XY"}},
            "points": [{"id": f"p{i}", "x": x, "y": y} for i, (x, y) in enumerate(corners)],
            "entities": [
                {"type": "line", "id": f"e{i}", "start": f"p{i}", "end": f"p{(i + 1) % 4}"}
                for i in range(4)
            ],
        },
    )
    plate = _add(
        session,
        job,
        "extrude",
        {"sketch": plate_sketch, "extent": {"type": "distance", "forward": 6.0}},
    )
    found = recognize_run(job, RecognizeParams(scan_key="scan:edge"))
    shapes = sorted(feature.shape for feature in found.features)
    assert shapes == ["circle", "cutCircle", "profile"]
    built = recognize_build(
        job,
        BuildParams(
            scan_key="scan:edge",
            base_revision=session.document.revision,
            features=list(range(len(found.features))),
            target_body=plate,
        ),
    )
    assert built.added and not built.skipped
    statuses = session.snapshot("current", job).status.features
    assert all(statuses[f].state == "ok" for f in built.added), {
        f: statuses[f].error for f in built.added
    }
    # Every sketch stays on the scan where its outlines were measured.
    for feature in session.document.features:
        if feature.id in built.added and feature.type == "sketch":
            assert statuses[feature.id].stats["sketch.deviation"] < 2 * NOISE
    body = session.built(job).result.bodies[plate]
    assert check_solid(body.shape).is_usable
    assert check_solid(body.shape).volume == pytest.approx(
        check_solid(edge_part()).volume, rel=2e-3
    )


# Design intent: the direction pad ------------------------------------------------------------


def _rotated(shape: TopoDS_Shape, degrees: float, x: float, y: float) -> TopoDS_Shape:
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), np.radians(degrees))
    return BRepBuilderAPI_Transform(shape, turn, True).Shape()


def pad_part() -> TopoDS_Shape:
    """60 x 60 x 5 plate: four 1.5 mm arms of a ring R 9-14 split by 3 mm wide diagonal
    gaps, around a D10 x 1.5 centre button, all centred at (30, 30)."""
    ring = BRepAlgoAPI_Cut(_cylinder(30, 30, 5, 28, 1.5), _cylinder(30, 30, 4, 18, 3)).Shape()
    for angle in (45.0, 135.0):
        gap = _rotated(_box(10, 28.5, 4, 50, 31.5, 8), angle, 30, 30)
        ring = BRepAlgoAPI_Cut(ring, gap).Shape()
    shape = BRepAlgoAPI_Fuse(_box(0, 0, 0, 60, 60, 5), ring).Shape()
    return BRepAlgoAPI_Fuse(shape, _cylinder(30, 30, 5, 10, 1.5)).Shape()


def test_the_arms_of_a_direction_pad_are_equal_around_the_centre_button() -> None:
    vertices, faces = _scan(pad_part(), 17)
    features = _top(recognize(vertices, faces, NOISE), height=5.0)
    arms = [f for f in features if f.outline.kind == "ringSegment"]
    button = next(f for f in features if f.outline.kind == "circle")
    assert len(arms) == 4
    for name in ("inner", "outer", "sweep", "gap", "corner"):
        values = {arm.outline.named()[name] for arm in arms}
        assert len(values) == 1, (name, values)
    p = arms[0].outline.named()
    assert p["inner"] == pytest.approx(9.0, abs=0.1)
    assert p["outer"] == pytest.approx(14.0, abs=0.1)
    assert p["gap"] == pytest.approx(3.0, abs=0.15)
    for arm in arms:
        assert arm.outline.center == button.outline.center
    assert button.outline.named()["radius"] == pytest.approx(5.0, abs=0.1)
