"""Alignment inputs as datums in scan coordinates.

Fit features, regions and stored face sets are refitted from their triangles here,
unconstrained: a fit's fixed direction, relation or snapped offset are expressed in
part coordinates, which depend on the alignment being computed. Reference features
(mid-planes, axes from two planes, ...) are evaluated by the rebuild engine in scan
coordinates, on top of such unconstrained fits.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

import numpy as np

from m2c_kernel.alignment.frames import Datum
from m2c_kernel.alignment.params import (
    AlignmentInput,
    FacesInput,
    FeatureInput,
    InputRole,
    RegionInput,
)
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.document.model import Alignment, Document, Feature
from m2c_kernel.features.common import STANDARD_NAMES
from m2c_kernel.fitting.api import (
    Cone,
    Cylinder,
    FitError,
    FitResult,
    Plane,
    Primitive,
    PrimitiveKind,
    Sphere,
    Torus,
    fit_best,
    fit_primitive,
    robust_sigma,
    signed_distance,
)
from m2c_kernel.geometry import IDENTITY, FloatArray, unit
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue, from_json
from m2c_kernel.session.jobs import JobContext, seeded_rng

MAX_INPUT_FACES = 200_000
"""Larger inputs are subsampled evenly; the datum does not get more accurate beyond this."""
_INPUT_KINDS: tuple[PrimitiveKind, ...] = ("plane", "cylinder", "cone", "sphere", "torus")
_AUTO_KINDS: tuple[PrimitiveKind, ...] = ("plane", "sphere", "cylinder", "cone")
_COORDINATE_FREE_FIXED = ("radius", "halfAngleDeg", "majorRadius", "minorRadius")


@dataclass(frozen=True)
class ScanGeometry:
    """The scan in scan coordinates, as the alignment reads it."""

    key: str
    vertices: FloatArray
    faces: np.ndarray
    usable: np.ndarray
    """Faces that are not synthetic (hole fills)."""
    noise: float


@dataclass(frozen=True)
class InputFit:
    """How one alignment input was fitted."""

    role: InputRole
    kind: str
    """Fitted primitive type, or `plane`, `axis`, `point` for reference geometry."""
    rms: float | None
    face_count: int


def resolve_input(
    document: Document, ref: AlignmentInput, role: InputRole, scan: ScanGeometry, job: JobContext
) -> tuple[Datum, InputFit]:
    """The datum of one input and how well it was fitted."""
    blobs = job.session.blobs
    match ref:
        case FeatureInput(feature=feature_id):
            feature = document.feature(feature_id)
            if feature is None or feature.suppressed:
                raise KernelError(ErrorCode.INPUT_NOT_FOUND, {"input": role})
            if feature.type == "reference":
                return _reference_datum(document, feature, role, job)
            if feature.type != "fit":
                raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
            params = _object(feature.params)
            kind = str(params.get("kind"))
            faces_ref = params.get("faces")
            if kind not in _INPUT_KINDS or not isinstance(faces_ref, str):
                raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
            faces = blobs.get(faces_ref).astype(np.int64)
            return _fitted_datum(faces, cast(PrimitiveKind, kind), role, scan)
        case RegionInput(region=region_id):
            region = next((item for item in document.regions.items if item.id == region_id), None)
            if region is None or document.regions.labels is None:
                raise KernelError(ErrorCode.INPUT_NOT_FOUND, {"input": role})
            if region.kind not in _INPUT_KINDS:
                raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
            labels = blobs.get(document.regions.labels)
            faces = np.nonzero(labels == region.label)[0].astype(np.int64)
            return _fitted_datum(faces, cast(PrimitiveKind, region.kind), role, scan)
        case FacesInput(faces=faces_ref):
            faces = blobs.get(faces_ref).astype(np.int64)
            return _fitted_datum(faces, None, role, scan)
    raise KernelError(ErrorCode.INVALID_PARAMS)


def _object(value: JsonValue) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _fitted_datum(
    faces: np.ndarray, kind: PrimitiveKind | None, role: InputRole, scan: ScanGeometry
) -> tuple[Datum, InputFit]:
    faces = faces[(faces >= 0) & (faces < len(scan.faces))]
    faces = faces[scan.usable[faces]]
    if len(faces) < MIN_FIT_FACES:
        raise KernelError(
            ErrorCode.TOO_FEW_FACES, {"input": role, "count": len(faces), "min": MIN_FIT_FACES}
        )
    if len(faces) > MAX_INPUT_FACES:
        faces = faces[:: int(np.ceil(len(faces) / MAX_INPUT_FACES))]
    corners = scan.vertices[scan.faces[faces]]
    points = corners.mean(axis=1)
    normals = unit(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]))
    rng = seeded_rng(f"alignment.input:{scan.key}:{len(faces)}:{kind}:{faces[:8].tolist()}")
    try:
        fit = _trimmed_fit(kind, points, normals, scan.noise, rng)
    except FitError as error:
        raise KernelError(ErrorCode.FIT_FAILED, {"input": role}) from error
    datum = datum_of(fit.primitive, role, normals)
    return datum, InputFit(role=role, kind=fit.kind, rms=fit.rms, face_count=fit.point_count)


def _trimmed_fit(
    kind: PrimitiveKind | None,
    points: FloatArray,
    normals: FloatArray,
    noise: float,
    rng: np.random.Generator,
) -> FitResult:
    """Fit, drop points beyond three robust sigmas (stray triangles), fit again."""
    if kind is None:
        fit, _ = fit_best(points, normals, rng, noise=noise, kinds=_AUTO_KINDS)
        kind = fit.kind
    else:
        fit = fit_primitive(kind, points, normals, rng)
    residual = np.abs(signed_distance(fit.primitive, points))
    keep = residual <= max(3.0 * robust_sigma(residual), 2.0 * noise)
    if keep.sum() < MIN_FIT_FACES or keep.all():
        return fit
    return fit_primitive(kind, points[keep], normals[keep], rng)


def datum_of(primitive: Primitive, role: str, normals: FloatArray | None = None) -> Datum:
    """Plane (normal into the material), axis or point of a primitive."""
    match primitive:
        case Plane(origin=origin, normal=normal):
            outward = unit(np.asarray(normal))
            if normals is not None and float(normals.sum(axis=0) @ outward) < 0:
                outward = -outward
            return Datum("plane", np.asarray(origin, dtype=np.float64), -outward, role)
        case Cylinder(origin=origin, axis=axis) | Torus(center=origin, axis=axis):
            return Datum("axis", np.asarray(origin, dtype=np.float64), unit(axis), role)
        case Cone(apex=apex, axis=axis):
            return Datum("axis", np.asarray(apex, dtype=np.float64), unit(axis), role)
        case Sphere(center=center):
            return Datum("point", np.asarray(center, dtype=np.float64), np.zeros(3), role)
    raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})


def _reference_datum(
    document: Document, feature: Feature, role: InputRole, job: JobContext
) -> tuple[Datum, InputFit]:
    """Evaluate a reference feature in scan coordinates on unconstrained fits."""
    from m2c_kernel.document.rebuild import rebuild

    session = job.session
    chain = scan_chain(document, feature.id, session.feature_types)
    if chain is None:
        raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
    scan_document = replace(document, alignment=Alignment(), features=chain)
    environment = replace(session.environment(), evaluate_alignment=lambda _d, _j: IDENTITY)
    result = rebuild(scan_document, environment, job, stop_after=feature.id)
    status = result.statuses.get(feature.id)
    output = result.outputs.get(feature.id)
    if status is None or status.state not in ("ok", "warning") or output is None:
        raise KernelError(ErrorCode.FIT_FAILED, {"input": role})
    construction = output.construction
    if construction is None:
        raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
    primitive = construction.primitive
    if isinstance(primitive, Plane):
        # A constructed plane has no material side; its normal is used as constructed.
        origin = np.asarray(primitive.origin, dtype=np.float64)
        datum = Datum("plane", origin, unit(np.asarray(primitive.normal)), role)
    elif primitive is not None:
        datum = datum_of(primitive, role)
    elif construction.axis is not None:
        axis = construction.axis
        datum = Datum("axis", np.asarray(axis.point), unit(axis.direction), role)
    elif construction.point is not None:
        datum = Datum("point", np.asarray(construction.point, dtype=np.float64), np.zeros(3), role)
    else:
        raise KernelError(ErrorCode.UNSUPPORTED_INPUT, {"input": role})
    return datum, InputFit(role=role, kind=datum.kind, rms=None, face_count=0)


def scan_chain(
    document: Document, feature_id: str, feature_types: Mapping[str, Any]
) -> tuple[Feature, ...] | None:
    """The features a reference needs, with fits made coordinate-free, in history order.

    None when the chain contains anything but fits and references, or refers to a
    standard plane or axis (which only exists in part coordinates).
    """
    by_id = {feature.id: feature for feature in document.features}
    needed: set[str] = set()
    pending = [feature_id]
    while pending:
        current_id = pending.pop()
        if current_id in needed:
            continue
        current = by_id.get(current_id)
        if current is None or current.suppressed or current.type not in ("fit", "reference"):
            return None
        if current.type == "reference" and _mentions_standard_geometry(current.params):
            return None
        needed.add(current.id)
        if current.type == "reference":
            spec = feature_types[current.type]
            refs = spec.references(from_json(current.params, spec.params_type))
            pending.extend(refs.features)
    return tuple(
        _coordinate_free(feature) if feature.type == "fit" else feature
        for feature in document.features
        if feature.id in needed
    )


def _mentions_standard_geometry(value: JsonValue) -> bool:
    if isinstance(value, str):
        return value in STANDARD_NAMES
    if isinstance(value, list):
        return any(_mentions_standard_geometry(item) for item in value)
    if isinstance(value, dict):
        return any(_mentions_standard_geometry(item) for item in value.values())
    return False


def _coordinate_free(feature: Feature) -> Feature:
    """A fit without the constraints that are expressed in part coordinates."""
    params = dict(_object(feature.params))
    fixed = _object(params.get("fixed"))
    params["fixed"] = {key: fixed[key] for key in _COORDINATE_FREE_FIXED if key in fixed}
    params["relation"] = None
    params["snap"] = False
    params["rejectedSnaps"] = []
    return replace(feature, params=cast(JsonValue, params))


def input_cache_key(document: Document, ref: AlignmentInput) -> str:
    """Everything an input's datum depends on besides the scan."""
    match ref:
        case FeatureInput(feature=feature_id):
            feature = document.feature(feature_id)
            if feature is None:
                return f"missing:{feature_id}"
            related = [feature] if feature.type != "reference" else list(document.features)
            state = [[item.id, item.type, item.suppressed, item.params] for item in related]
            return json.dumps([feature_id, state], sort_keys=True)
        case RegionInput(region=region_id):
            region = next((item for item in document.regions.items if item.id == region_id), None)
            kind = region.kind if region is not None else None
            label = region.label if region is not None else None
            return json.dumps([region_id, document.regions.labels, kind, label])
        case FacesInput(faces=faces_ref):
            return faces_ref
    return ""
