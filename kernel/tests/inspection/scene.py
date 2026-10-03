"""Session documents with a synthetic scan, test bodies and test fits.

`testBody` puts a named OCCT solid into the document; `testFit` fits a primitive to
stored scan triangles like the real fit feature (same `faces` parameter), so measure
can derive uncertainties from it. The noisy scan of the test block is displaced along
the exact surface normal of each triangle's B-Rep face, so the true signed distance of
every vertex is known.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from functools import cache

import numpy as np
import numpy.typing as npt

from m2c_kernel.cad.occ_compat import BRepPrimAPI_MakeBox, TopoDS_Shape
from m2c_kernel.document.model import Document, DocumentSettings, Feature, Scan, ScanSource
from m2c_kernel.document.rebuild import EvalContext
from m2c_kernel.document.results import Body, BodyUpdate, Construction, FeatureOutput
from m2c_kernel.features.registry import FeatureTypeSpec, ReadSet, Refs, temporary_feature_type
from m2c_kernel.fitting.api import PrimitiveKind, fit_primitive
from m2c_kernel.geometry import vec3
from m2c_kernel.protocol.wire import BlobRef
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.synthetic.parts import SyntheticPart, block_part, build_test_block

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

SIGMA = 0.03
"""Scan noise of the acceptance targets (ARCHITECTURE.md 1.5)."""


@cache
def _block_shape() -> TopoDS_Shape:
    return build_test_block()


SHAPES: dict[str, Callable[[], TopoDS_Shape]] = {
    "block": _block_shape,
    "box": lambda: BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape(),
}


@dataclass(frozen=True, kw_only=True)
class BodyParams:
    shape: str


@dataclass(frozen=True, kw_only=True)
class FitParams:
    faces: BlobRef
    kind: PrimitiveKind


def _body(ctx: EvalContext, params: BodyParams) -> FeatureOutput:
    shape = SHAPES[params.shape]()
    return FeatureOutput(bodies=BodyUpdate(changed={ctx.feature_id: Body(shape)}))


def _fit(ctx: EvalContext, params: FitParams) -> FeatureOutput:
    mesh = ctx.mesh
    vertices = np.unique(mesh.faces[ctx.face_set(params.faces)].ravel())
    result = fit_primitive(
        params.kind, mesh.vertices[vertices], mesh.vertex_normals[vertices], ctx.rng
    )
    return FeatureOutput(construction=Construction(primitive=result.primitive))


BODY = FeatureTypeSpec(
    type_id="testBody",
    params_type=BodyParams,
    input_type=BodyParams,
    reads=ReadSet(),
    references=lambda params: Refs(),
    evaluate=_body,
    store=lambda value, blobs: value,
    module=__name__,
)
FIT = FeatureTypeSpec(
    type_id="testFit",
    params_type=FitParams,
    input_type=FitParams,
    reads=ReadSet(mesh=True),
    references=lambda params: Refs(),
    evaluate=_fit,
    store=lambda value, blobs: value,
    module=__name__,
)


@contextmanager
def registered_types() -> Iterator[None]:
    """Register `testBody` and `testFit` for the duration of a test."""
    with ExitStack() as stack:
        stack.enter_context(temporary_feature_type(BODY))
        stack.enter_context(temporary_feature_type(FIT))
        yield


@dataclass(frozen=True)
class NoisyScan:
    vertices: FloatArray
    faces: IntArray
    labels: IntArray
    """B-Rep face per triangle."""
    offset: FloatArray
    """True signed distance of every vertex (positive outside)."""


@cache
def noisy_block(max_edge: float = 1.0, sigma: float = SIGMA, seed: int = 7) -> NoisyScan:
    """The test block scan with Gaussian noise along the exact surface normal.

    Vertices on B-Rep edges stay on the surface (their normal is ambiguous), so the
    offset is exact for every vertex.
    """
    part: SyntheticPart = block_part(max_edge)
    rng = np.random.default_rng(seed)
    normals, single_face = _surface_normals(part)
    offset = rng.normal(0.0, sigma, len(part.vertices)) * single_face
    return NoisyScan(
        vertices=part.vertices + normals * offset[:, None],
        faces=part.faces,
        labels=part.labels,
        offset=offset,
    )


def _surface_normals(part: SyntheticPart) -> tuple[FloatArray, npt.NDArray[np.float64]]:
    """Outward normal of the analytic surface at every vertex, and 1 where it is unique."""
    from m2c_kernel.fitting.api import surface_normals

    normals = np.zeros_like(part.vertices)
    owners = np.full(len(part.vertices), -1)
    shared = np.zeros(len(part.vertices), dtype=bool)
    for face_id in np.unique(part.labels):
        vertices = np.unique(part.faces[part.labels == face_id].ravel())
        shared[vertices[owners[vertices] >= 0]] = True
        owners[vertices] = face_id
    for face_id, surface in enumerate(part.surfaces):
        rows = np.flatnonzero(owners == face_id)
        if surface is None or len(rows) == 0:
            continue
        normals[rows] = surface_normals(surface, part.vertices[rows])
    # The analytic normal points out of convex primitives; flip it where it points into
    # the material, detected with the triangle winding (faces are outward).
    triangle_normals = np.cross(
        part.vertices[part.faces[:, 1]] - part.vertices[part.faces[:, 0]],
        part.vertices[part.faces[:, 2]] - part.vertices[part.faces[:, 0]],
    )
    vertex_normals = np.zeros_like(part.vertices)
    for corner in range(3):
        np.add.at(vertex_normals, part.faces[:, corner], triangle_normals)
    flip = np.einsum("ij,ij->i", normals, vertex_normals) < 0
    normals[flip] *= -1.0
    return normals, (~shared & (owners >= 0)).astype(np.float64)


def scan_document(
    session: Session,
    vertices: FloatArray,
    faces: IntArray,
    *,
    synthetic: npt.NDArray[np.bool_] | None = None,
    tolerance: float = 0.1,
) -> Document:
    """A document whose scan is the given mesh (scan coordinates = part coordinates)."""
    origin = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    blobs = session.blobs
    scan = Scan(
        key=f"scan:test{len(vertices)}",
        source=ScanSource(file_name="test.stl", sha256="0" * 64, import_unit="mm"),
        vertices=blobs.put((vertices - origin).astype(np.float32)),
        faces=blobs.put(faces.astype(np.uint32)),
        synthetic=None if synthetic is None else blobs.put(synthetic.astype(np.uint8)),
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=vec3(origin),
        noise=SIGMA,
    )
    return replace(Document.empty(), scan=scan, settings=DocumentSettings(tolerance=tolerance))


def feature(feature_id: str, type_id: str, **params: object) -> Feature:
    return Feature(id=feature_id, type=type_id, name=None, suppressed=False, params=dict(params))


def commit(session: Session, document: Document, *features: Feature) -> Document:
    """Commit the document with the features appended; returns the committed document."""
    job = JobContext.detached(session)
    document = replace(document, features=(*document.features, *features))
    session.commit(document, "test", job)
    return session.document


def face_set(session: Session, faces: IntArray) -> BlobRef:
    return session.blobs.put(np.asarray(faces, dtype=np.uint32))
