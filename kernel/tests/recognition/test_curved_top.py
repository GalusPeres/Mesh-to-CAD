"""A direction pad's arm: its top slopes down to the pad's centre on a cone, built to fit."""

from __future__ import annotations

from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.TopoDS import TopoDS_Shape

from m2c_kernel.cad.check import check_solid
from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Fuse,
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeRevol,
    gp_Ax1,
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
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

NOISE = 0.005
TOP = 8.0
CENTRE = (30.0, 25.0)
INNER, OUTER = 8.0, 14.0
SLOPE = np.tan(np.radians(10.0))
"""The arm's top rises by 10 degrees away from the pad's centre."""


@cache
def part_shape() -> TopoDS_Shape:
    """60 x 50 x 8 plate with one arm: a 90 degree ring sector, 1 mm high at its inner
    edge and rising outwards on a cone."""
    profile = BRepBuilderAPI_MakePolygon()
    x0, y0 = CENTRE
    for r, z in (
        (INNER, TOP - 0.5),
        (OUTER, TOP - 0.5),
        (OUTER, TOP + 1.0 + SLOPE * (OUTER - INNER)),
        (INNER, TOP + 1.0),
    ):
        profile.Add(gp_Pnt(x0 + r, y0, z))
    profile.Close()
    face = BRepBuilderAPI_MakeFace(profile.Wire()).Face()
    axis = gp_Ax1(gp_Pnt(x0, y0, 0.0), gp_Dir(0, 0, 1))
    arm = BRepPrimAPI_MakeRevol(face, axis, np.radians(90.0)).Shape()
    plate = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 60.0, 50.0, TOP).Shape()
    return BRepAlgoAPI_Fuse(plate, arm).Shape()


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    op = AddFeature(feature=NewFeature(type=type_id, params=RawObject(params)))
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=[op], label="t"))
    return session.document.features[-1].id


def test_the_arm_is_built_up_to_its_conical_top(session: Session, job: JobContext) -> None:
    part = tessellate_part(part_shape(), max_edge=0.5)
    normals = vertex_normals(part.vertices, part.faces)
    vertices = add_scanner_noise(part.vertices, normals, NOISE, np.random.default_rng(5))
    scan = Scan(
        key="scan:arm",
        source=ScanSource("arm.stl", "0", "mm"),
        vertices=session.blobs.put(vertices.astype(np.float32)),
        faces=session.blobs.put(part.faces.astype(np.uint32)),
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(part.faces),
        origin=(0.0, 0.0, 0.0),
        noise=NOISE,
    )
    session.commit(replace(Document.empty(), scan=scan), "import", job)
    corners = [(0.0, 0.0), (60.0, 0.0), (60.0, 50.0), (0.0, 50.0)]
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

    found = recognize_run(job, RecognizeParams(scan_key="scan:arm"))
    arms = [f for f in found.features if f.kind == "boss"]
    assert len(arms) == 1
    assert arms[0].shape == "ringSegment"
    assert arms[0].top == "inclined"
    assert np.degrees(arms[0].tilt) == pytest.approx(10.0, abs=1.0)

    built = recognize_build(
        job,
        BuildParams(
            scan_key="scan:arm",
            base_revision=session.document.revision,
            features=[found.features.index(arms[0])],
            target_body=plate,
        ),
    )
    types = [f.type for f in session.document.features if f.id in built.added]
    assert "freeformPatch" in types and "trim" in types and "combine" in types
    statuses = session.snapshot("current", job).status.features
    assert all(statuses[feature].state != "error" for feature in built.added)
    body = session.built(job).result.bodies[plate]
    assert check_solid(body.shape).is_usable
    # A flat top at the arm's mean height would be off by about 1 mm^3 per mm^2.
    assert check_solid(body.shape).volume == pytest.approx(
        check_solid(part_shape()).volume, rel=2e-3
    )
