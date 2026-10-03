"""Recognised outlines, templates and free chains alike, become valid sketch loops of the
right area, and recognised features build the part."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Cut,
    BRepAlgoAPI_Fuse,
    BRepGProp,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    GProp_GProps,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
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
from m2c_kernel.protocol.wire import RawObject, from_json
from m2c_kernel.recognition.chain import Chain, chain_points
from m2c_kernel.recognition.outline import Outline, free_outline
from m2c_kernel.recognition.sketch_ops import SketchDraft, chain_loop
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from m2c_kernel.sketch.api import evaluate, section_geometry
from m2c_kernel.sketch.params import PlanarSection, SketchParams, StandardPlaneSource
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

SHAPES = [
    Outline("circle", (3.0, -2.0, 4.0), 0.0),
    Outline("cutCircle", (1.0, 2.0, 3.6, 0.1, 1.6), 0.0),
    Outline("slot", (0.0, 1.0, 0.3, 8.0, 4.8), 0.0),
    Outline("roundedRect", (-1.0, 0.0, 0.2, 12.0, 6.0, 1.5), 0.0),
    Outline("roundedRect", (2.0, 1.0, 0.0, 10.0, 4.0, 0.0), 0.0),
    Outline("ringSegment", (0.0, 0.0, 9.0, 14.0, 0.5, 1.2, 0.0, 0.0), 0.0),
    Outline("ringSegment", (0.0, 0.0, 8.65, 13.35, np.pi / 4, np.pi / 2, 5.9, 0.8), 0.0),
]


def _polygon_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * abs(x @ np.roll(y, -1) - y @ np.roll(x, -1)))


def _star() -> Chain:
    """A free profile: a fitted five-pointed star of lines and arcs."""
    t = np.linspace(0, 2 * np.pi, 600, endpoint=False)
    star = (5 + 2 * np.cos(5 * t))[:, None] * np.column_stack([np.cos(t), np.sin(t)])
    return free_outline(star, 0.02).chain


CHAINS = [shape.chain for shape in SHAPES] + [_star()]


@pytest.mark.parametrize("chain", CHAINS, ids=[*(s.kind for s in SHAPES), "profile"])
def test_outline_becomes_one_closed_loop_of_the_same_area(chain: Chain) -> None:
    sketch = SketchDraft()
    loop = chain_loop(sketch, chain, np.zeros(2))
    section = PlanarSection(plane=StandardPlaneSource(plane="XY"))
    params = from_json(
        {
            "section": {"type": "planar", "plane": {"type": "standard", "plane": "XY"}},
            "points": sketch.points,
            "entities": sketch.entities,
            "constraints": sketch.constraints,
        },
        SketchParams,
    )
    result = evaluate(params, section_geometry(section, lambda _: None))  # type: ignore[arg-type]
    assert not result.profile.open_entities
    assert [found.id for found in result.profile.loops] == [loop]
    assert len(result.profiles.profile_faces) == 1
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(result.profiles.profile_faces[0], properties)
    expected = _polygon_area(chain_points(chain, step_deg=0.25))
    assert properties.Mass() == pytest.approx(expected, rel=2e-3)


# Building through the commands ------------------------------------------------------------


def _panel_shape() -> Any:
    """80 x 50 x 6 plate: two D8 x 2 buttons, a D12 x 3 recess with a D5 x 1.5 button."""
    shape = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 80.0, 50.0, 6.0).Shape()
    for x in (15.0, 30.0):
        shape = BRepAlgoAPI_Fuse(shape, _cylinder(x, 35.0, 6.0, 8.0, 2.0)).Shape()
    shape = BRepAlgoAPI_Cut(shape, _cylinder(55.0, 25.0, 3.0, 12.0, 10.0)).Shape()
    shape = BRepAlgoAPI_Fuse(shape, _cylinder(55.0, 25.0, 3.0, 5.0, 1.5)).Shape()
    return BRepAlgoAPI_Cut(shape, _cylinder(10.0, 10.0, -1.0, 6.0, 10.0)).Shape()


def _cylinder(x: float, y: float, z: float, diameter: float, height: float) -> Any:
    axis = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, diameter / 2.0, height).Shape()


def _scan_document(session: Session, vertices: np.ndarray, faces: np.ndarray) -> Document:
    return replace(
        Document.empty(),
        scan=Scan(
            key="scan:panel",
            source=ScanSource("panel.stl", "0", "mm"),
            vertices=session.blobs.put(vertices.astype(np.float32)),
            faces=session.blobs.put(faces.astype(np.uint32)),
            synthetic=None,
            vertex_count=len(vertices),
            face_count=len(faces),
            origin=(0.0, 0.0, 0.0),
            noise=0.02,
        ),
    )


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    op = AddFeature(feature=NewFeature(type=type_id, params=RawObject(params)))
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=[op], label="t"))
    return session.document.features[-1].id


def test_recognised_features_build_the_part_on_a_plate(session: Session, job: JobContext) -> None:
    shape = _panel_shape()
    part = tessellate_part(shape, max_edge=0.8)
    rng = np.random.default_rng(3)
    noisy = add_scanner_noise(part.vertices, vertex_normals(part.vertices, part.faces), 0.02, rng)
    session.commit(_scan_document(session, noisy, part.faces), "import", job)

    # The plain plate as the body the features are added to and cut from.
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

    found = recognize_run(job, RecognizeParams(scan_key="scan:panel"))
    # The recess's label sits on its rim, clear of the button inside it.
    inner = next(f for f in found.features if f.parent is not None)
    recess = found.features[inner.parent or 0]
    assert np.hypot(*np.subtract(recess.label, inner.label)[:2]) == pytest.approx(6.0, abs=0.3)
    chosen = list(range(len(found.features)))
    built = recognize_build(
        job,
        BuildParams(
            scan_key="scan:panel",
            base_revision=session.document.revision,
            features=chosen,
            target_body=plate,
        ),
    )
    assert built.added and not built.skipped
    statuses = session.snapshot("current", job).status.features
    assert all(statuses[feature].state == "ok" for feature in built.added), {
        feature: statuses[feature].error for feature in built.added
    }
    body = session.built(job).result.bodies[plate]
    assert check_solid(body.shape).is_usable
    # Rounded design values (0.05 mm) and noise: within half a percent of the part.
    assert check_solid(body.shape).volume == pytest.approx(check_solid(shape).volume, rel=5e-3)


def test_without_a_body_every_button_becomes_a_body(session: Session, job: JobContext) -> None:
    shape = _panel_shape()
    part = tessellate_part(shape, max_edge=0.8)
    rng = np.random.default_rng(5)
    noisy = add_scanner_noise(part.vertices, vertex_normals(part.vertices, part.faces), 0.02, rng)
    session.commit(_scan_document(session, noisy, part.faces), "import", job)
    found = recognize_run(job, RecognizeParams(scan_key="scan:panel"))
    buttons = [
        i
        for i, feature in enumerate(found.features)
        if feature.kind == "boss" and feature.parent is None and feature.shape == "circle"
    ]
    assert len(buttons) == 2
    built = recognize_build(
        job,
        BuildParams(
            scan_key="scan:panel",
            base_revision=session.document.revision,
            features=buttons,
            names=["Knopf", "Knopf"],
        ),
    )
    statuses = session.snapshot("current", job).status.features
    assert all(statuses[feature].state == "ok" for feature in built.added)
    named = [f.name for f in session.document.features if f.type == "extrude"]
    assert named == ["Knopf", "Knopf"]
    bodies = session.built(job).result.bodies
    assert len(bodies) == 2
    for body in bodies.values():
        # D8 x 2 buttons.
        assert check_solid(body.shape).volume == pytest.approx(np.pi * 16.0 * 2.0, rel=0.03)
