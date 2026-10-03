"""Radius of rounded edges from the scan, against synthetic parts with known radii."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import cache
from typing import Any

import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.GC import GC_MakeArcOfCircle
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from scipy.spatial import cKDTree

from m2c_kernel.cad.edge_frames import edge_frames
from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism, gp_Pnt, gp_Vec
from m2c_kernel.commands.doc import ApplyParams, doc_apply
from m2c_kernel.commands.fillet import ScanRadiusParams, fillet_scan_radius
from m2c_kernel.document.model import Document, Scan, ScanSource
from m2c_kernel.document.ops import AddFeature, NewFeature
from m2c_kernel.features.types.fillet import EdgeRef
from m2c_kernel.fitting.corner import EdgeRadius, edge_radius
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.wire import RawObject
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic.noise import add_scanner_noise
from tests.synthetic.parts import tessellate_part

pytestmark = pytest.mark.occt

HEIGHT = 4.0


def _edges(shape: TopoDS_Shape, keep: Callable[[Any, Any], bool]) -> list[TopoDS_Shape]:
    found = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        if keep(curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())):
            found.append(edge)
        explorer.Next()
    return found


def _top(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    return _edges(shape, lambda a, b: abs(a.Z() - HEIGHT) < 1e-6 and abs(b.Z() - HEIGHT) < 1e-6)


def _rounded(shape: TopoDS_Shape, radius: float) -> TopoDS_Shape:
    maker = BRepFilletAPI_MakeFillet(shape)
    for edge in _top(shape):
        maker.Add(radius, edge)
    return maker.Shape()


@cache
def _box() -> TopoDS_Shape:
    """10 x 4 x 4: short top edges, like a button's (the corners where they meet keep the
    radii small)."""
    return BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10.0, 4.0, HEIGHT).Shape()


@cache
def _plate() -> TopoDS_Shape:
    """A 40 x 20 rounded rectangle (R5 corners), 4 high: one top outline of 8 edges."""
    w, h, r = 40.0, 20.0, 5.0
    wire = BRepBuilderAPI_MakeWire()
    straight = [
        ((r, 0), (w - r, 0)),
        ((w, r), (w, h - r)),
        ((w - r, h), (r, h)),
        ((0, h - r), (0, r)),
    ]
    corners = [((w - r, r), -45), ((w - r, h - r), 45), ((r, h - r), 135), ((r, r), 225)]
    for (start, end), (centre, angle) in zip(straight, corners, strict=True):
        wire.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*start, 0), gp_Pnt(*end, 0)).Edge())
        a = np.radians(angle)
        middle = gp_Pnt(centre[0] + r * np.cos(a), centre[1] + r * np.sin(a), 0)
        arc_end = {-45: (w, r), 45: (w - r, h), 135: (0, h - r), 225: (r, 0)}[angle]
        arc = GC_MakeArcOfCircle(gp_Pnt(*end, 0), middle, gp_Pnt(*arc_end, 0)).Value()
        wire.Add(BRepBuilderAPI_MakeEdge(arc).Edge())
    face = BRepBuilderAPI_MakeFace(wire.Wire()).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, HEIGHT)).Shape()


def _scan(shape: TopoDS_Shape, noise: float, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    part = tessellate_part(shape, max_edge=0.4)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, noise, np.random.default_rng(seed))
    return noisy, part.faces


def _measure(model: TopoDS_Shape, edges: list[TopoDS_Shape], scan: np.ndarray) -> EdgeRadius:
    result = edge_radius(scan, cKDTree(scan), edge_frames(model, edges), 0.02)
    assert result is not None
    return result


@pytest.mark.parametrize("radius", [0.3, 0.5, 0.75])
def test_a_short_straight_edge(radius: float) -> None:
    scan, _ = _scan(_rounded(_box(), radius), 0.02)
    four_mm = _edges(
        _box(),
        lambda a, b: min(a.Z(), b.Z()) > HEIGHT - 1e-6 and max(abs(a.X()), abs(b.X())) < 1e-6,
    )
    result = _measure(_box(), four_mm[:1], scan)
    assert result.radius == pytest.approx(radius, abs=0.03)
    assert result.rms < 0.04


def test_a_long_closed_outline_of_lines_and_arcs() -> None:
    scan, _ = _scan(_rounded(_plate(), 1.0), 0.02)
    result = _measure(_plate(), _top(_plate()), scan)
    assert result.radius == pytest.approx(1.0, abs=0.03)
    assert result.samples >= 48
    assert result.spread[1] - result.spread[0] < 0.1


def test_a_noisy_scan() -> None:
    scan, _ = _scan(_rounded(_plate(), 0.8), 0.05, seed=4)
    result = _measure(_plate(), _top(_plate()), scan)
    assert result.radius == pytest.approx(0.8, abs=0.06)


def test_model_faces_off_the_scan() -> None:
    """The modelled top lies 0.15 mm below the scanned one, a wall 0.1 mm inside."""
    scan, _ = _scan(_rounded(_plate(), 1.0), 0.02)
    shifted = scan + np.array([0.0, 0.0, 0.15])
    result = _measure(_plate(), _top(_plate()), shifted)
    assert result.radius == pytest.approx(1.0, abs=0.05)


def test_a_sharp_edge_reads_zero() -> None:
    scan, _ = _scan(_box(), 0.02)
    result = _measure(_box(), _top(_box()), scan)
    assert result.radius == 0.0


# Through the command ----------------------------------------------------------------------


def _add(session: Session, job: JobContext, type_id: str, params: dict[str, Any]) -> str:
    op = AddFeature(feature=NewFeature(type=type_id, params=RawObject(params)))
    doc_apply(job, ApplyParams(base_revision=session.document.revision, ops=[op], label="t"))
    return session.document.features[-1].id


def test_the_command_measures_and_snaps(session: Session, job: JobContext) -> None:
    vertices, faces = _scan(_rounded(_box(), 0.75), 0.02)
    scan = Scan(
        key="scan:box",
        source=ScanSource("box.stl", "0", "mm"),
        vertices=session.blobs.put(vertices.astype(np.float32)),
        faces=session.blobs.put(faces.astype(np.uint32)),
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=(0.0, 0.0, 0.0),
        noise=0.02,
    )
    session.commit(replace(Document.empty(), scan=scan), "import", job)
    corners = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)]
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
    body = _add(
        session, job, "extrude", {"sketch": sketch, "extent": {"type": "distance", "forward": 4}}
    )
    edges = [
        EdgeRef(faces=(f"{body}:cap:end", f"{body}:side:e{i}"), point=point)
        for i, point in enumerate([(5.0, 0.0, 4.0), (10.0, 2.0, 4.0)])
    ]
    result = fillet_scan_radius(job, ScanRadiusParams(target_body=body, edges=edges))
    assert result.radius == pytest.approx(0.75)
    assert result.measured == pytest.approx(0.75, abs=0.03)
    assert result.samples >= 10
