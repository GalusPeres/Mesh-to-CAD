"""Public API of the scan alignment.

The alignment is a slot of the document, evaluated first in every rebuild. Its
inputs are fitted in scan coordinates, so fit features referenced as inputs are
refitted from their stored triangles here (never from their own results, which
are in part coordinates and depend on the alignment).

Methods (`Alignment.method`):
- `none`: identity, then the adjustment.
- `auto`: largest plane -> XY (material above it), largest plane within 10 degrees of
  perpendicular -> XZ (material behind it), origin at the bounding-box minimum, snapped
  onto those planes. PCA with the third-moment sign rule when fewer planes exist.
- `faces`: 3-2-1 frame from fit features or regions (`FacesAlignmentParams`).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from m2c_kernel.alignment.frames import (
    Datum,
    FrameError,
    adjustment_rotation,
    angle_deg,
    apply,
    in_plane_direction,
    make_transform,
    origin_from_datums,
    pca_rows,
    rows_from_datums,
    skew_sign,
    surface_moments,
)
from m2c_kernel.alignment.params import AlignmentInputRef, FacesAlignmentParams
from m2c_kernel.alignment.planes import PlaneCandidate, detect_planes
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.document.model import Alignment, AlignmentAdjust, Document
from m2c_kernel.fitting.api import FitError, fit_primitive
from m2c_kernel.geometry import IDENTITY, FloatArray, Matrix4, matrix_tuple, unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import from_json
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext, seeded_rng

PERPENDICULAR_SIN = float(np.sin(np.radians(10.0)))
"""The secondary plane of the automatic alignment is within 10 degrees of perpendicular."""
TIE_RATIO = 0.9
"""Opposite planes whose areas differ by less than 10 % are a tie, decided by the skew rule."""
ORIGIN_SNAP_MM = 1.0
"""A frame plane this close to the bounding-box minimum becomes the origin coordinate."""
_MAX_AXIS_FACES = 400_000


@dataclass(frozen=True)
class InputFit:
    """How well one alignment input was refitted."""

    role: str
    kind: str
    rms: float
    point_count: int


@dataclass(frozen=True)
class AlignmentEvaluation:
    """The transform of an alignment and what the panels show about it."""

    matrix: Matrix4
    inputs: tuple[InputFit, ...] = ()
    largest_plane_tilt_deg: float | None = None
    plane_count: int = 0
    fallback: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanGeometry:
    """The scan in scan coordinates, as the alignment reads it."""

    vertices: FloatArray
    faces: np.ndarray
    usable: np.ndarray
    """Faces that are not synthetic (hole fills)."""
    band: float


def evaluate_alignment(document: Document, job: JobContext) -> Matrix4:
    """Return the scan-to-part transform for the document's alignment slot."""
    if document.alignment.method == "none" and document.alignment.adjust == AlignmentAdjust():
        return IDENTITY
    return evaluate(document, document.alignment, job.session.blobs).matrix


_cache: OrderedDict[str, AlignmentEvaluation] = OrderedDict()
_plane_cache: OrderedDict[str, list[PlaneCandidate]] = OrderedDict()
_CACHE_SIZE = 16


def evaluate(document: Document, alignment: Alignment, blobs: BlobStore) -> AlignmentEvaluation:
    """Evaluate an alignment (committed or previewed); cached by its inputs."""
    scan = document.scan
    if scan is None:
        if alignment.method == "none":
            return AlignmentEvaluation(matrix=IDENTITY)
        raise KernelError(DocumentError.NO_SCAN)
    key = _cache_key(document, alignment)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    geometry = _scan_geometry(document, blobs)
    planes = _planes(scan.key, geometry)
    try:
        if alignment.method == "auto":
            result = _auto(geometry, planes, alignment.adjust)
        elif alignment.method == "faces":
            result = _faces(document, alignment, geometry, blobs)
        else:
            rotation = np.eye(4)
            rotation[:3, :3] = adjustment_rotation(alignment.adjust)
            result = AlignmentEvaluation(matrix=matrix_tuple(rotation))
    except FrameError as error:
        raise KernelError(error.code) from error
    if planes:
        z_part = np.asarray(result.matrix).reshape(4, 4)[:3, :3] @ planes[0].normal
        tilt = angle_deg(z_part, np.array([0.0, 0.0, 1.0]))
        result = AlignmentEvaluation(
            matrix=result.matrix,
            inputs=result.inputs,
            largest_plane_tilt_deg=tilt,
            plane_count=len(planes),
            fallback=result.fallback,
        )
    _cache[key] = result
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return result


def _cache_key(document: Document, alignment: Alignment) -> str:
    assert document.scan is not None
    parts: list[Any] = [
        document.scan.key,
        alignment.method,
        alignment.params,
        [alignment.adjust.flip_x, alignment.adjust.flip_z, alignment.adjust.rotate_z90],
    ]
    if alignment.method == "faces":
        parts.append([feature.params for feature in document.features if feature.type == "fit"])
        parts.append(document.regions.labels)
    return json.dumps(parts, sort_keys=True, default=str)


def _scan_geometry(document: Document, blobs: BlobStore) -> ScanGeometry:
    scan = document.scan
    assert scan is not None
    vertices = blobs.get(scan.vertices).astype(np.float64) + np.asarray(scan.origin)
    faces = blobs.get(scan.faces).astype(np.int64)
    usable = np.ones(len(faces), dtype=bool)
    if scan.synthetic is not None:
        usable = ~blobs.get(scan.synthetic).astype(bool)
    noise = document.settings.noise_override or scan.noise or 0.03
    return ScanGeometry(vertices, faces, usable, band=max(0.15, 4.0 * noise))


def _planes(scan_key: str, geometry: ScanGeometry) -> list[PlaneCandidate]:
    cached = _plane_cache.get(scan_key)
    if cached is None:
        rng = seeded_rng(f"alignment.planes:{scan_key}")
        cached = detect_planes(
            geometry.vertices, geometry.faces, geometry.band, rng, geometry.usable
        )
        _plane_cache[scan_key] = cached
        while len(_plane_cache) > 4:
            _plane_cache.popitem(last=False)
    return cached


def auto_rows(
    vertices: FloatArray, faces: np.ndarray, planes: list[PlaneCandidate]
) -> tuple[FloatArray, list[PlaneCandidate], bool]:
    """Axes of the automatic alignment, the planes used as datums and whether PCA was used."""
    if not planes:
        rows, _ = pca_rows(vertices, faces)
        return rows, [], True
    primary = planes[0]
    z = -primary.normal
    side = [plane for plane in planes[1:] if abs(float(plane.normal @ z)) < PERPENDICULAR_SIN]
    if not side:
        x = in_plane_direction(z, vertices, faces)
        return np.stack([x, np.cross(z, x), z]), [primary], True
    secondary = side[0]
    ties = [
        plane
        for plane in side[1:]
        if plane.area >= TIE_RATIO * secondary.area
        and float(plane.normal @ secondary.normal) < -0.9
    ]
    if ties:
        _, _, area, centred = surface_moments(vertices, faces)
        y_candidate = unit(-secondary.normal + float(secondary.normal @ z) * z)
        if skew_sign(y_candidate, area, centred) < 0:
            secondary = ties[0]
    y = unit(-secondary.normal - float(-secondary.normal @ z) * z)
    return np.stack([np.cross(y, z), y, z]), [primary, secondary], False


def _auto(
    geometry: ScanGeometry, planes: list[PlaneCandidate], adjust: AlignmentAdjust
) -> AlignmentEvaluation:
    vertices, faces = geometry.vertices, geometry.faces[geometry.usable]
    rows, datums, fallback = auto_rows(vertices, faces, planes)
    rotation = adjustment_rotation(adjust) @ rows
    transform = make_transform(rotation, np.zeros(3))
    transform = rebased(transform, vertices, datums)
    inputs = tuple(
        InputFit(role=role, kind="plane", rms=plane.rms, point_count=len(plane.faces))
        for role, plane in zip(("primary", "secondary"), datums, strict=False)
    )
    return AlignmentEvaluation(matrix=matrix_tuple(transform), inputs=inputs, fallback=fallback)


def rebased(
    transform: FloatArray, vertices: FloatArray, planes: list[PlaneCandidate]
) -> FloatArray:
    """Move the origin to the bounding-box minimum; a frame plane near it takes its place."""
    result = transform.copy()
    minimum = apply(transform, vertices).min(axis=0)
    rotation = transform[:3, :3]
    for axis in range(3):
        for plane in planes:
            normal = rotation @ plane.normal
            if abs(normal[axis]) < 1 - 1e-9:
                continue
            offset = float(apply(transform, plane.point[None])[0, axis])
            if abs(offset - minimum[axis]) <= ORIGIN_SNAP_MM:
                minimum[axis] = offset
    result[:3, 3] -= minimum
    return result


def _faces(
    document: Document, alignment: Alignment, geometry: ScanGeometry, blobs: BlobStore
) -> AlignmentEvaluation:
    try:
        params = from_json(alignment.params, FacesAlignmentParams)
    except (TypeError, ValueError, KeyError) as error:
        raise KernelError(ErrorCode.INVALID_PARAMS) from error
    refs = [("primary", params.primary), ("secondary", params.secondary)]
    if params.tertiary is not None:
        refs.append(("tertiary", params.tertiary))
    datums: list[Datum] = []
    inputs: list[InputFit] = []
    for role, ref in refs:
        datum, fit = input_datum(document, ref, role, geometry, blobs)
        datums.append(datum)
        inputs.append(fit)
    vertices, faces = geometry.vertices, geometry.faces[geometry.usable]
    datums = orient_axes(datums, vertices, faces)
    rows = rows_from_datums(datums[0], datums[1:], vertices, faces)
    origin = origin_from_datums(rows, datums, vertices, require_point=len(datums) == 3)
    rotation = adjustment_rotation(alignment.adjust) @ rows
    transform = make_transform(rotation, origin)
    return AlignmentEvaluation(matrix=matrix_tuple(transform), inputs=tuple(inputs))


def orient_axes(datums: list[Datum], vertices: FloatArray, faces: np.ndarray) -> list[Datum]:
    """Give fitted axes (whose sign is arbitrary) a deterministic sign by the skew rule."""
    _, _, area, centred = surface_moments(vertices, faces)
    result = []
    for datum in datums:
        if datum.kind == "axis":
            direction = unit(datum.direction)
            datum = Datum("axis", datum.point, direction * skew_sign(direction, area, centred))
        result.append(datum)
    return result


def input_datum(
    document: Document, ref: AlignmentInputRef, role: str, geometry: ScanGeometry, blobs: BlobStore
) -> tuple[Datum, InputFit]:
    """Refit the triangles of a fit feature or region in scan coordinates."""
    face_ids, kind = _input_faces(document, ref, blobs)
    face_ids = face_ids[(face_ids >= 0) & (face_ids < len(geometry.faces))]
    face_ids = face_ids[geometry.usable[face_ids]]
    if len(face_ids) > _MAX_AXIS_FACES:
        face_ids = face_ids[:: int(np.ceil(len(face_ids) / _MAX_AXIS_FACES))]
    if len(face_ids) < 6:
        raise KernelError(ErrorCode.FIT_FAILED, {"input": role})
    corners = geometry.vertices[geometry.faces[face_ids]]
    points = corners.mean(axis=1)
    normals = unit(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]))
    rng = seeded_rng(f"alignment.input:{document.scan.key if document.scan else ''}:{role}")
    try:
        fit = fit_primitive(kind, points, normals, rng)  # type: ignore[arg-type]
    except FitError as error:
        raise KernelError(ErrorCode.FIT_FAILED, {"input": role}) from error
    primitive: Any = fit.primitive
    info = InputFit(role=role, kind=kind, rms=fit.rms, point_count=fit.point_count)
    if kind == "plane":
        normal = unit(np.asarray(primitive.normal))
        if float((normals @ normal).sum()) < 0:
            normal = -normal
        return Datum("plane", np.asarray(primitive.origin), -normal), info
    point = primitive.apex if kind == "cone" else primitive.origin
    return Datum("axis", np.asarray(point), unit(np.asarray(primitive.axis))), info


_AXIS_KINDS = ("cylinder", "cone")


def _input_faces(
    document: Document, ref: AlignmentInputRef, blobs: BlobStore
) -> tuple[np.ndarray, str]:
    if (ref.feature is None) == (ref.region is None):
        raise KernelError(ErrorCode.INVALID_PARAMS)
    if ref.feature is not None:
        feature = document.feature(ref.feature)
        if feature is None or feature.suppressed:
            raise KernelError(ErrorCode.INPUT_NOT_FOUND, {"input": ref.feature})
        params = feature.params if isinstance(feature.params, dict) else {}
        kind = str(params.get("kind", ""))
        faces_ref = params.get("faces")
        if feature.type != "fit" or not isinstance(faces_ref, str):
            raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": ref.feature})
        if kind not in ("plane", *_AXIS_KINDS):
            raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": ref.feature, "kind": kind})
        return blobs.get(faces_ref).astype(np.int64), kind
    region = next((item for item in document.regions.items if item.id == ref.region), None)
    if region is None or document.regions.labels is None:
        raise KernelError(ErrorCode.INPUT_NOT_FOUND, {"input": ref.region})
    if region.kind not in ("plane", *_AXIS_KINDS):
        raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": ref.region, "kind": region.kind})
    labels = blobs.get(document.regions.labels)
    return np.nonzero(labels == region.label)[0].astype(np.int64), region.kind
