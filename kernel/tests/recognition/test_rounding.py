"""Rounded and inclined button tops: measured, grouped and built (fillets, fitted planes)."""

from __future__ import annotations

from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Common,
    BRepAlgoAPI_Fuse,
    BRepBuilderAPI_MakeFace,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeHalfSpace,
    gp_Ax2,
    gp_Dir,
    gp_Pln,
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
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.recognition.api import Recognition, recognize
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

NOISE = 0.005
"""Like a scanner's smoothed mesh; the rounding is tessellated far finer than a scan, and
more noise would scramble its triangles' normals."""
TOP = 8.0
"""Height of the plate; the buttons stand 2 mm on it."""
RADIUS = 0.5
TILT_DEG = 6.0


def _button(x: float, y: float, height: float = 2.0) -> TopoDS_Shape:
    """A D8 button `height` high on the plate (reaching 0.5 mm into it)."""
    axis = gp_Ax2(gp_Pnt(x, y, TOP - 0.5), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, 4.0, height + 0.5).Shape()


def _rounded_top(shape: TopoDS_Shape, above: float) -> TopoDS_Shape:
    """`shape` with every circular edge above height `above` rounded by `RADIUS`."""
    maker = BRepFilletAPI_MakeFillet(shape)
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        ends = (curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter()))
        if min(end.Z() for end in ends) > above:
            maker.Add(RADIUS, edge)
        explorer.Next()
    return maker.Shape()


def _inclined(x: float, y: float) -> TopoDS_Shape:
    """A D8 button whose top drops by `TILT_DEG` towards -x (about 2 mm high at its centre)."""
    slope = np.radians(TILT_DEG)
    normal = gp_Dir(-np.sin(slope), 0.0, np.cos(slope))
    plane = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(x, y, TOP + 2.0), normal)).Face()
    below = BRepPrimAPI_MakeHalfSpace(plane, gp_Pnt(x, y, TOP)).Solid()
    return BRepAlgoAPI_Common(_button(x, y, 3.0), below).Shape()


@cache
def part_shape() -> TopoDS_Shape:
    """70 x 30 x 8 plate: two rounded D8 buttons and one inclined D8 button."""
    plate = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 70.0, 30.0, TOP).Shape()
    shape = plate
    for x in (12.0, 30.0):
        shape = BRepAlgoAPI_Fuse(shape, _rounded_top(_button(x, 15.0), TOP + 1.0)).Shape()
    return BRepAlgoAPI_Fuse(shape, _inclined(52.0, 15.0)).Shape()


@cache
def scan() -> tuple[np.ndarray, np.ndarray]:
    part = tessellate_part(part_shape(), max_edge=0.6)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, NOISE, np.random.default_rng(11))
    return noisy, part.faces


@cache
def recognition() -> Recognition:
    vertices, faces = scan()
    return recognize(vertices, faces, NOISE)


def _buttons() -> list[int]:
    found = recognition()
    return [
        i
        for i, feature in enumerate(found.features)
        if feature.relief.kind == "boss" and abs(found.planes[feature.plane].normal[2]) > 0.99
    ]


def test_rounded_buttons_share_one_measured_radius() -> None:
    found = recognition()
    flat = [i for i in _buttons() if found.features[i].relief.top == "flat"]
    assert len(flat) == 2
    assert found.groups[flat[0]] == found.groups[flat[1]]
    for index in flat:
        rounding = found.roundings[index]
        assert rounding is not None
        assert rounding.radius == pytest.approx(RADIUS, abs=0.05)
    assert found.radii[found.groups[flat[0]]] == pytest.approx(RADIUS)


def test_an_inclined_top_is_found_with_its_tilt() -> None:
    found = recognition()
    inclined = [i for i in _buttons() if found.features[i].relief.top == "inclined"]
    assert len(inclined) == 1
    relief = found.features[inclined[0]].relief
    assert relief.top_surface is not None and relief.top_surface.planar
    assert np.degrees(relief.tilt) == pytest.approx(TILT_DEG, abs=0.5)
    assert relief.height == pytest.approx(2.0, abs=0.1)
    # Its sharp top edge needs no fillet.
    assert found.radii[found.groups[inclined[0]]] == 0.0


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    op = AddFeature(feature=NewFeature(type=type_id, params=RawObject(params)))
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=[op], label="t"))
    return session.document.features[-1].id


def test_building_rounds_the_buttons_and_follows_the_inclined_top(
    session: Session, job: JobContext
) -> None:
    vertices, faces = scan()
    document = replace(
        Document.empty(),
        scan=Scan(
            key="scan:buttons",
            source=ScanSource("buttons.stl", "0", "mm"),
            vertices=session.blobs.put(vertices.astype(np.float32)),
            faces=session.blobs.put(faces.astype(np.uint32)),
            synthetic=None,
            vertex_count=len(vertices),
            face_count=len(faces),
            origin=(0.0, 0.0, 0.0),
            noise=NOISE,
        ),
    )
    session.commit(document, "import", job)
    corners = [(0.0, 0.0), (70.0, 0.0), (70.0, 30.0), (0.0, 30.0)]
    sketch = _add(
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
        session, job, "extrude", {"sketch": sketch, "extent": {"type": "distance", "forward": TOP}}
    )
    found = recognize_run(job, RecognizeParams(scan_key="scan:buttons"))
    tops = sorted(feature.top for feature in found.features if feature.kind == "boss")
    assert tops == ["flat", "flat", "inclined"]
    assert [f.rounding for f in found.features if f.top == "flat"] == [RADIUS, RADIUS]
    built = recognize_build(
        job,
        BuildParams(
            scan_key="scan:buttons",
            base_revision=session.document.revision,
            features=list(range(len(found.features))),
            target_body=plate,
        ),
    )
    assert not built.unrounded
    statuses = session.snapshot("current", job).status.features
    assert all(statuses[feature].state != "error" for feature in built.added), {
        feature: statuses[feature].error for feature in built.added
    }
    kinds = [f.type for f in session.document.features if f.id in built.added]
    assert kinds.count("fillet") == 1  # one per group: the two round buttons
    body = session.built(job).result.bodies[plate]
    assert check_solid(body.shape).is_usable
    assert check_solid(body.shape).volume == pytest.approx(
        check_solid(part_shape()).volume, rel=2e-3
    )
