"""Evaluation of the feature history.

Features are evaluated in history order. Each result is cached under a result
key: a hash of the feature type, its canonical parameters, the keys of the
results and bodies it references, and whatever its `ReadSet` declares (scan,
alignment, settings). An unchanged feature is a cache hit, so a parameter change
re-evaluates only that feature and its dependents, and a change of the project
tolerance re-evaluates only the features that read it.

A failed feature leaves the bodies unchanged and carries its error; features
that depend on it are skipped, independent later features still evaluate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import traceback
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.cad import ErrorCode as CadError
from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.kernel import ErrorCode as KernelErrorCode
from m2c_kernel.document.model import Document, DocumentSettings, Feature
from m2c_kernel.document.results import (
    Body,
    Construction,
    ErrorInfo,
    FeatureOutput,
    FeatureStatus,
    SketchResult,
)
from m2c_kernel.features.registry import FeatureTypeSpec, Refs
from m2c_kernel.geometry import FloatArray, Matrix4, transform_points
from m2c_kernel.protocol.errors import Cancelled, KernelError
from m2c_kernel.protocol.wire import BlobRef, from_json
from m2c_kernel.session.jobs import JobContext, seeded_rng

if TYPE_CHECKING:
    from scipy.spatial import cKDTree

    from m2c_kernel.cad.check import SolidCheck
    from m2c_kernel.mesh.normals import JetFit
    from m2c_kernel.mesh.topology import EdgeTopology, FaceGraph
    from m2c_kernel.session.blobs import BlobStore

log = logging.getLogger(__name__)

type IntArray = npt.NDArray[np.int64]


class EvalMesh:
    """The scan in part coordinates. Derived data is computed on first use and kept."""

    def __init__(
        self,
        key: str,
        vertices: FloatArray,
        faces: IntArray,
        synthetic: npt.NDArray[np.bool_] | None,
    ) -> None:
        self.key = key
        self.vertices = vertices
        self.faces = faces
        self.synthetic = synthetic if synthetic is not None else np.zeros(len(faces), dtype=bool)

    @cached_property
    def _face_geometry(self) -> tuple[FloatArray, FloatArray]:
        from m2c_kernel.mesh.normals import face_normals

        return face_normals(self.vertices, self.faces)

    @property
    def face_normals(self) -> FloatArray:
        return self._face_geometry[0]

    @property
    def face_areas(self) -> FloatArray:
        return self._face_geometry[1]

    @cached_property
    def face_centroids(self) -> FloatArray:
        centroids: FloatArray = self.vertices[self.faces].mean(axis=1)
        return centroids

    @cached_property
    def vertex_normals(self) -> FloatArray:
        from m2c_kernel.mesh.normals import vertex_normals

        return vertex_normals(self.vertices, self.faces)

    @cached_property
    def jet(self) -> JetFit:
        """Jet-fit normals, curvature and residuals (use these normals for fitting)."""
        from m2c_kernel.mesh.normals import jet_fit

        return jet_fit(self.vertices, self.vertex_normals)

    @cached_property
    def topology(self) -> EdgeTopology:
        from m2c_kernel.mesh.topology import edge_topology

        return edge_topology(self.faces)

    @cached_property
    def face_graph(self) -> FaceGraph:
        from m2c_kernel.mesh.topology import FaceGraph

        return FaceGraph(self.topology)

    @cached_property
    def vertex_tree(self) -> cKDTree:
        from scipy.spatial import cKDTree

        return cKDTree(self.vertices)


class MeshProvider:
    """Builds `EvalMesh` objects and keeps the most recent ones, with their derived data."""

    def __init__(self, blobs: BlobStore, capacity: int = 2) -> None:
        self._blobs = blobs
        self._capacity = capacity
        self._meshes: OrderedDict[str, EvalMesh] = OrderedDict()

    def get(self, document: Document, matrix: Matrix4) -> EvalMesh | None:
        scan = document.scan
        if scan is None:
            return None
        key = mesh_key(scan.key, matrix)
        mesh = self._meshes.get(key)
        if mesh is None:
            local = self._blobs.get(scan.vertices).astype(np.float64)
            vertices = transform_points(matrix, local + np.asarray(scan.origin))
            faces = self._blobs.get(scan.faces).astype(np.int64)
            synthetic = None
            if scan.synthetic is not None:
                synthetic = self._blobs.get(scan.synthetic).astype(bool)
            mesh = EvalMesh(key, vertices, faces, synthetic)
            self._meshes[key] = mesh
            while len(self._meshes) > self._capacity:
                self._meshes.popitem(last=False)
        self._meshes.move_to_end(key)
        return mesh


def mesh_key(scan_key: str, matrix: Matrix4) -> str:
    digest = hashlib.sha256(scan_key.encode("utf-8"))
    digest.update(np.asarray(matrix, dtype=np.float64).tobytes())
    return f"mesh:{digest.hexdigest()[:24]}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass
class _EvalState:
    """Results of the features evaluated so far."""

    statuses: dict[str, FeatureStatus] = field(default_factory=dict)
    outputs: dict[str, FeatureOutput] = field(default_factory=dict)
    result_keys: dict[str, str] = field(default_factory=dict)
    bodies: dict[str, Body] = field(default_factory=dict)
    body_keys: dict[str, str] = field(default_factory=dict)
    body_owner: dict[str, str] = field(default_factory=dict)
    body_checks: dict[str, SolidCheck] = field(default_factory=dict)

    def usable(self, feature_id: str) -> bool:
        status = self.statuses.get(feature_id)
        return status is not None and status.state in ("ok", "warning")


class EvalContext:
    """What a feature's `evaluate` may read. Everything is in part coordinates."""

    def __init__(
        self,
        *,
        feature_id: str,
        result_key: str,
        job: JobContext,
        blobs: BlobStore,
        settings: DocumentSettings,
        mesh: EvalMesh | None,
        state: _EvalState,
    ) -> None:
        self.feature_id = feature_id
        self.result_key = result_key
        self.job = job
        self.blobs = blobs
        self.settings = settings
        self._mesh = mesh
        self._state = state

    @property
    def mesh(self) -> EvalMesh:
        if self._mesh is None:
            raise KernelError(DocumentError.NO_SCAN)
        return self._mesh

    @cached_property
    def rng(self) -> np.random.Generator:
        """Random generator seeded from the result key: equal inputs give equal results."""
        return seeded_rng(self.result_key)

    def face_set(self, ref: BlobRef) -> IntArray:
        return self.blobs.get(ref).astype(np.int64)

    def output(self, feature_id: str) -> FeatureOutput:
        output = self._state.outputs.get(feature_id)
        if output is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature_id})
        return output

    def construction(self, feature_id: str) -> Construction:
        construction = self.output(feature_id).construction
        if construction is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature_id})
        return construction

    def sketch(self, feature_id: str) -> SketchResult:
        sketch = self.output(feature_id).sketch
        if sketch is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": feature_id})
        return sketch

    def body(self, body_id: str) -> Body:
        body = self._state.bodies.get(body_id)
        if body is None:
            raise KernelError(DocumentError.INPUT_UNAVAILABLE, {"feature": body_id})
        return body


@dataclass(frozen=True)
class RebuildResult:
    statuses: Mapping[str, FeatureStatus]
    outputs: Mapping[str, FeatureOutput]
    result_keys: Mapping[str, str]
    bodies: Mapping[str, Body]
    body_keys: Mapping[str, str]
    body_owner: Mapping[str, str]
    body_checks: Mapping[str, SolidCheck]
    matrix: Matrix4
    mesh: EvalMesh | None


@dataclass(frozen=True)
class CachedResult:
    output: FeatureOutput
    checks: Mapping[str, SolidCheck]
    """Validity check of every body the output changed, by body id."""


class ResultCache:
    """Feature outputs by result key (LRU). Previews and commits share it."""

    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._items: OrderedDict[str, CachedResult] = OrderedDict()

    def get(self, key: str) -> CachedResult | None:
        item = self._items.get(key)
        if item is not None:
            self._items.move_to_end(key)
        return item

    def put(self, key: str, result: CachedResult) -> None:
        self._items[key] = result
        self._items.move_to_end(key)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)


type AlignmentEvaluator = Callable[[Document, JobContext], Matrix4]


@dataclass
class RebuildEnvironment:
    blobs: BlobStore
    results: ResultCache
    meshes: MeshProvider
    feature_types: Mapping[str, FeatureTypeSpec]
    evaluate_alignment: AlignmentEvaluator


def rebuild(
    document: Document,
    env: RebuildEnvironment,
    job: JobContext,
    stop_after: str | None = None,
) -> RebuildResult:
    """Evaluate the history; with `stop_after`, stop after that feature (previews)."""
    matrix = env.evaluate_alignment(document, job)
    mesh = env.meshes.get(document, matrix)
    state = _EvalState()
    for feature in document.features:
        job.check_cancelled()
        _evaluate_feature(feature, document, env, job, mesh, matrix, state)
        if feature.id == stop_after:
            break
    return RebuildResult(
        statuses=state.statuses,
        outputs=state.outputs,
        result_keys=state.result_keys,
        bodies=state.bodies,
        body_keys=state.body_keys,
        body_owner=state.body_owner,
        body_checks=state.body_checks,
        matrix=matrix,
        mesh=mesh,
    )


def _evaluate_feature(
    feature: Feature,
    document: Document,
    env: RebuildEnvironment,
    job: JobContext,
    mesh: EvalMesh | None,
    matrix: Matrix4,
    state: _EvalState,
) -> None:
    if feature.suppressed:
        state.statuses[feature.id] = FeatureStatus(state="suppressed")
        return
    spec = env.feature_types.get(feature.type)
    if spec is None:
        error = ErrorInfo(DocumentError.UNKNOWN_FEATURE_TYPE, {"type": feature.type})
        state.statuses[feature.id] = FeatureStatus(state="error", error=error)
        return
    try:
        params: Any = from_json(feature.params, spec.params_type)
    except KernelError as failure:
        state.statuses[feature.id] = FeatureStatus(state="error", error=_error_info(failure))
        return

    refs = spec.references(params)
    unusable = [ref for ref in (*refs.features, *refs.bodies) if not state.usable(ref)]
    if unusable:
        error = ErrorInfo(DocumentError.INPUT_UNAVAILABLE, {"feature": unusable[0]})
        state.statuses[feature.id] = FeatureStatus(state="skipped", error=error)
        return

    key = _result_key(feature, spec, refs, mesh, matrix, document.settings, state)
    cached = env.results.get(key)
    if cached is None:
        context = EvalContext(
            feature_id=feature.id,
            result_key=key,
            job=job,
            blobs=env.blobs,
            settings=document.settings,
            mesh=mesh,
            state=state,
        )
        try:
            output = spec.evaluate(context, params)
            cached = CachedResult(output, _check_bodies(output))
        except Cancelled:
            raise
        except KernelError as failure:
            state.statuses[feature.id] = FeatureStatus(state="error", error=_error_info(failure))
            return
        except Exception:
            log.exception("feature %s (%s) failed", feature.id, feature.type)
            error = ErrorInfo(KernelErrorCode.INTERNAL, details=traceback.format_exc())
            state.statuses[feature.id] = FeatureStatus(state="error", error=error)
            return
        env.results.put(key, cached)

    output = cached.output
    state.outputs[feature.id] = output
    state.result_keys[feature.id] = key
    for body_id, body in output.bodies.changed.items():
        state.bodies[body_id] = body
        state.body_keys[body_id] = f"{key}:{body_id}"
        state.body_owner[body_id] = feature.id
        state.body_checks[body_id] = cached.checks[body_id]
    for body_id in output.bodies.removed:
        state.bodies.pop(body_id, None)
        state.body_keys.pop(body_id, None)
        state.body_owner.pop(body_id, None)
        state.body_checks.pop(body_id, None)
    issues = tuple(output.issues)
    state.statuses[feature.id] = FeatureStatus(
        state="warning" if issues else "ok",
        issues=issues,
        stats=dict(output.stats),
    )


def _check_bodies(output: FeatureOutput) -> dict[str, SolidCheck]:
    """Every body a feature produces must be one valid solid with positive volume."""
    if not output.bodies.changed:
        return {}
    from m2c_kernel.cad.check import check_solid

    checks: dict[str, SolidCheck] = {}
    for body_id, body in output.bodies.changed.items():
        check = check_solid(body.shape)
        if not check.is_usable:
            raise KernelError(
                CadError.INVALID_RESULT,
                {"body": body_id, "solids": check.solids, "valid": check.valid},
            )
        checks[body_id] = check
    return checks


def _result_key(
    feature: Feature,
    spec: FeatureTypeSpec,
    refs: Refs,
    mesh: EvalMesh | None,
    matrix: Matrix4,
    settings: DocumentSettings,
    state: _EvalState,
) -> str:
    digest = hashlib.sha256()
    digest.update(feature.type.encode("utf-8"))
    digest.update(canonical_json(feature.params).encode("utf-8"))
    for ref in refs.features:
        digest.update(state.result_keys[ref].encode("utf-8"))
    for ref in refs.bodies:
        digest.update(state.body_keys.get(ref, ref).encode("utf-8"))
    if spec.reads.mesh:
        digest.update((mesh.key if mesh is not None else "no-scan").encode("utf-8"))
    elif spec.reads.alignment:
        digest.update(np.asarray(matrix, dtype=np.float64).tobytes())
    for name in spec.reads.settings:
        digest.update(f"{name}={getattr(settings, name)!r}".encode())
    return f"r:{digest.hexdigest()[:32]}"


def _error_info(error: KernelError) -> ErrorInfo:
    return ErrorInfo(error.code, dict(error.params), error.details)
