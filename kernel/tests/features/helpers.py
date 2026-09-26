"""Test-only upstream feature types and document builders for the solid features.

`testSketch` stands in for the sketch package: it returns rectangle profiles
with named edges (the `SketchResult.edge_names` contract) and a line table.
`testConstruction` stands in for fits and reference geometry.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np

from m2c_kernel.document.model import Document, DocumentSettings, Feature, Scan, ScanSource
from m2c_kernel.document.results import (
    Construction,
    DisplaySource,
    FeatureOutput,
    PlaneFrame,
    SketchResult,
)
from m2c_kernel.features.registry import FeatureTypeSpec, ReadSet, Refs, temporary_feature_type
from m2c_kernel.fitting.api import Axis, Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import FloatArray
from m2c_kernel.session.session import Session
from tests.cad.profiles import XY, XZ, polygon, rectangle_corners

FRAMES = {"XY": XY, "XZ": XZ}


@dataclass(frozen=True)
class NamedSketchResult(SketchResult):
    """`SketchResult` with the fields of interface request T6 (edge names, line table)."""

    edge_names: tuple[tuple[str, ...], ...] = ()
    lines: Mapping[str, tuple[FloatArray, FloatArray]] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Rect:
    loop: str
    x: float
    y: float
    width: float
    height: float
    holes: list[tuple[float, float, float]] = field(default_factory=list)
    """Circular holes (centre u, v and radius) inside the rectangle."""


@dataclass(frozen=True, kw_only=True)
class TestSketchParams:
    plane: Literal["XY", "XZ"] = "XY"
    rects: list[Rect]
    axis_line: tuple[tuple[float, float], tuple[float, float]] | None = None
    """A construction line `a0` in plane coordinates."""
    named: bool = True


def _with_holes(face: Any, holes: list[tuple[float, float, float]], frame: PlaneFrame) -> Any:
    from OCP.gp import gp_Circ

    from m2c_kernel.cad.occ_compat import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
        TopoDS,
        gp_Ax2,
        gp_Dir,
        gp_Pnt,
    )

    maker = BRepBuilderAPI_MakeFace(TopoDS.Face(face))
    for u, v, radius in holes:
        centre = frame.origin + u * frame.x_dir + v * frame.y_dir
        # Clockwise seen from the normal side: a hole.
        axis = gp_Ax2(gp_Pnt(*centre), gp_Dir(*(-frame.normal)), gp_Dir(*frame.x_dir))
        edge = BRepBuilderAPI_MakeEdge(gp_Circ(axis, radius)).Edge()
        maker.Add(TopoDS.Wire(BRepBuilderAPI_MakeWire(edge).Wire()))
    return maker.Face()


def _sketch(ctx: Any, params: TestSketchParams) -> FeatureOutput:
    frame = FRAMES[params.plane]
    faces, loop_ids, names = [], [], []
    for rect in params.rects:
        face = polygon(rectangle_corners(rect.x, rect.y, rect.width, rect.height), frame)
        if rect.holes:
            face = _with_holes(face, rect.holes, frame)
        faces.append(face)
        loop_ids.append(rect.loop)
        hole_names = [f"{rect.loop}h{k}" for k in range(len(rect.holes))]
        names.append(tuple([f"{rect.loop}e{k}" for k in range(4)] + hole_names))
    lines: dict[str, tuple[FloatArray, FloatArray]] = {}
    if params.axis_line is not None:
        (u0, v0), (u1, v1) = params.axis_line
        lines["a0"] = (
            frame.origin + u0 * frame.x_dir + v0 * frame.y_dir,
            frame.origin + u1 * frame.x_dir + v1 * frame.y_dir,
        )
    if params.named:
        result: SketchResult = NamedSketchResult(
            frame=frame,
            profile_faces=tuple(faces),
            loop_ids=tuple(loop_ids),
            edge_names=tuple(names),
            lines=lines,
        )
    else:
        result = SketchResult(frame=frame, profile_faces=tuple(faces), loop_ids=tuple(loop_ids))
    return FeatureOutput(sketch=result)


@dataclass(frozen=True, kw_only=True)
class TestConstructionParams:
    kind: Literal["plane", "cylinder", "cone", "sphere", "torus", "axis"]
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    radius: float = 0.0
    minor: float = 0.0
    half_angle_deg: float = 0.0
    covered: tuple[float, float] | None = None
    """Axial range the fit covers (drawn as its construction display)."""


def _primitive(params: TestConstructionParams) -> Primitive | None:
    match params.kind:
        case "plane":
            return Plane(origin=params.origin, normal=params.direction)
        case "cylinder":
            return Cylinder(origin=params.origin, axis=params.direction, radius=params.radius)
        case "cone":
            return Cone(
                apex=params.origin,
                axis=params.direction,
                half_angle=float(np.radians(params.half_angle_deg)),
            )
        case "sphere":
            return Sphere(center=params.origin, radius=params.radius)
        case "torus":
            return Torus(
                center=params.origin,
                axis=params.direction,
                major_radius=params.radius,
                minor_radius=params.minor,
            )
    return None


def _construction(ctx: Any, params: TestConstructionParams) -> FeatureOutput:
    primitive = _primitive(params)
    axis = None
    if params.kind == "axis":
        axis = Axis(point=params.origin, direction=params.direction)
    display: tuple[DisplaySource, ...] = ()
    if params.covered is not None:
        origin, direction = np.asarray(params.origin), np.asarray(params.direction)
        ends = origin + np.outer(params.covered, direction)
        display = (
            DisplaySource(
                kind="mesh",
                style="construction",
                positions=np.vstack([ends, ends + 1e-3]),
                indices=np.array([[0, 1, 2], [1, 3, 2]]),
            ),
        )
    return FeatureOutput(construction=Construction(primitive=primitive, axis=axis), display=display)


SKETCH = FeatureTypeSpec(
    type_id="testSketch",
    params_type=TestSketchParams,
    input_type=TestSketchParams,
    reads=ReadSet(),
    references=lambda params: Refs(),
    evaluate=_sketch,
    store=lambda value, blobs: value,
    module=__name__,
)
CONSTRUCTION = replace(
    SKETCH,
    type_id="testConstruction",
    params_type=TestConstructionParams,
    input_type=TestConstructionParams,
    evaluate=_construction,
)


@contextmanager
def upstream_test_types() -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(temporary_feature_type(SKETCH))
        stack.enter_context(temporary_feature_type(CONSTRUCTION))
        yield


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _json(value: Any) -> Any:
    if isinstance(value, tuple | list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    return value


def feature(feature_id: str, type_id: str, **params: Any) -> Feature:
    """A stored feature; top-level parameter names may be given in snake_case."""
    stored = {_camel(key): _json(value) for key, value in params.items()}
    return Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=stored)


def rect(loop: str, x: float, y: float, width: float, height: float) -> dict[str, Any]:
    return {"loop": loop, "x": x, "y": y, "width": width, "height": height}


def document(*features: Feature, scan: Scan | None = None, tolerance: float = 0.1) -> Document:
    return replace(
        Document.empty(),
        features=features,
        scan=scan,
        next_id=len(features) + 1,
        settings=DocumentSettings(tolerance=tolerance),
    )


def scan_of(session: Session, vertices: FloatArray, faces: np.ndarray) -> Scan:
    """A document scan from part-coordinate vertices (alignment: identity)."""
    origin = vertices.min(axis=0)
    local = (vertices - origin).astype(np.float32)
    return Scan(
        key=f"scan:test{len(vertices)}",
        source=ScanSource(file_name="test.stl", sha256="0" * 64, import_unit="mm"),
        vertices=session.blobs.put(local),
        faces=session.blobs.put(faces.astype(np.uint32)),
        synthetic=None,
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=(float(origin[0]), float(origin[1]), float(origin[2])),
        noise=None,
    )
