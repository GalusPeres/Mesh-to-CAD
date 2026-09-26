"""Public API of the scan alignment.

The alignment is a slot of the document, evaluated first in every rebuild
(`evaluate_alignment`). Methods (`Alignment.method`):

- `none`: identity, then the adjustment.
- `auto`: the largest plane becomes XY with the material above it, the largest plane
  within 10 degrees of perpendicular becomes XZ (material on the +Y side), the
  origin goes to the bounding-box minimum, snapped onto planes that lie there. With
  only one plane the in-plane direction is the principal direction of the scan;
  without planes the frame is the principal axes of the surface (PCA with the
  third-moment sign rule).
- `faces`: a 3-2-1 frame from fit features, reference features, regions or stored
  face sets (`FacesAlignmentParams`).

`adjust` then turns the part over, reverses X and Y, or rotates it in quarter turns.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.alignment.frames import (
    Datum,
    FrameError,
    Surface,
    adjustment_rotation,
    apply,
    build_frame,
    line_angle_deg,
    make_transform,
)
from m2c_kernel.alignment.inputs import InputFit, ScanGeometry, input_cache_key, resolve_input
from m2c_kernel.alignment.params import AlignmentInput, FacesAlignmentParams, InputRole
from m2c_kernel.alignment.planes import PlaneCandidate, detect_planes
from m2c_kernel.codes.alignment import ErrorCode, IssueCode, ProgressStage
from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.document.model import Alignment, AlignmentAdjust, Document
from m2c_kernel.geometry import IDENTITY, FloatArray, Matrix4, matrix_tuple
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import from_json
from m2c_kernel.session.jobs import JobContext, seeded_rng

__all__ = [
    "AlignmentEvaluation",
    "InputFit",
    "LargestPlane",
    "evaluate",
    "evaluate_alignment",
]

PERPENDICULAR_SIN = float(np.sin(np.radians(10.0)))
"""The secondary plane of the automatic alignment is within 10 degrees of perpendicular."""
AXIS_ALIGNED_COS = float(np.cos(np.radians(2.0)))
"""A plane this close to a part axis may define the origin coordinate along that axis."""
TIE_RATIO = 0.9
"""Opposite planes whose areas differ by less than 10 % are a tie, decided by the skew rule."""
ORIGIN_SNAP_MM = 1.0
"""A plane this close above the bounding-box minimum gives the origin coordinate."""

type PrincipalPlane = Literal["XY", "XZ", "YZ"]


@dataclass(frozen=True)
class LargestPlane:
    """The largest plane of the scan and its angle to the nearest principal plane."""

    plane: PrincipalPlane
    tilt_deg: float


@dataclass(frozen=True)
class AlignmentEvaluation:
    """The transform of an alignment and what the panels show about it."""

    matrix: Matrix4
    inputs: tuple[InputFit, ...] = ()
    largest_plane: LargestPlane | None = None
    plane_count: int = 0
    issues: tuple[str, ...] = ()


def evaluate_alignment(document: Document, job: JobContext) -> Matrix4:
    """Return the scan-to-part transform of the document's alignment slot."""
    alignment = document.alignment
    if alignment.method == "none" and alignment.adjust == AlignmentAdjust():
        return IDENTITY
    return evaluate(document, alignment, job).matrix


_CACHE_SIZE = 16
_evaluations: OrderedDict[str, AlignmentEvaluation] = OrderedDict()
_planes: OrderedDict[str, list[PlaneCandidate]] = OrderedDict()


def evaluate(document: Document, alignment: Alignment, job: JobContext) -> AlignmentEvaluation:
    """Evaluate an alignment (committed or previewed); results are cached by their inputs."""
    if document.scan is None:
        if alignment.method == "none":
            return AlignmentEvaluation(matrix=IDENTITY)
        raise KernelError(DocumentError.NO_SCAN)
    key = _evaluation_key(document, alignment)
    cached = _evaluations.get(key)
    if cached is not None:
        _evaluations.move_to_end(key)
        return cached
    scan = _scan_geometry(document, job)
    planes = scan_planes(scan, job)
    surface = Surface(scan.vertices, scan.faces[scan.usable])
    try:
        if alignment.method == "auto":
            transform, issues = _auto(scan, surface, planes, alignment.adjust)
            inputs: tuple[InputFit, ...] = ()
        elif alignment.method == "faces":
            transform, inputs = _faces(document, alignment, scan, surface, job)
            issues = ()
        else:
            transform = make_transform(adjustment_rotation(alignment.adjust), np.zeros(3))
            inputs, issues = (), ()
    except FrameError as error:
        raise KernelError(error.code, {"input": error.role} if error.role else {}) from error
    result = AlignmentEvaluation(
        matrix=matrix_tuple(transform),
        inputs=inputs,
        largest_plane=_largest_plane(transform, planes),
        plane_count=len(planes),
        issues=issues,
    )
    _evaluations[key] = result
    while len(_evaluations) > _CACHE_SIZE:
        _evaluations.popitem(last=False)
    return result


def scan_planes(scan: ScanGeometry, job: JobContext) -> list[PlaneCandidate]:
    """The large planes of a scan, largest first (cached per scan)."""
    cached = _planes.get(scan.key)
    if cached is not None:
        _planes.move_to_end(scan.key)
        return cached
    job.progress(None, ProgressStage.DETECTING_PLANES)
    band = max(0.15, 4.0 * scan.noise)
    rng = seeded_rng(f"alignment.planes:{scan.key}")
    planes = detect_planes(
        scan.vertices, scan.faces, band, rng, scan.usable, check_cancelled=job.check_cancelled
    )
    _planes[scan.key] = planes
    while len(_planes) > 4:
        _planes.popitem(last=False)
    return planes


def _evaluation_key(document: Document, alignment: Alignment) -> str:
    assert document.scan is not None
    adjust = alignment.adjust
    parts: list[object] = [
        document.scan.key,
        document.settings.noise_override,
        alignment.method,
        alignment.params,
        [adjust.flip_x, adjust.flip_z, adjust.rotate_z90],
    ]
    if alignment.method == "faces":
        params = _faces_params(alignment)
        refs = [params.primary, params.secondary, params.tertiary]
        parts.append([input_cache_key(document, ref) for ref in refs if ref is not None])
    return json.dumps(parts, sort_keys=True, default=str)


def _scan_geometry(document: Document, job: JobContext) -> ScanGeometry:
    scan = document.scan
    assert scan is not None
    blobs = job.session.blobs
    vertices = blobs.get(scan.vertices).astype(np.float64) + np.asarray(scan.origin)
    faces = blobs.get(scan.faces).astype(np.int64)
    usable = np.ones(len(faces), dtype=bool)
    if scan.synthetic is not None:
        usable = ~blobs.get(scan.synthetic).astype(bool)
    noise = document.settings.noise_override or scan.noise or 0.03
    return ScanGeometry(scan.key, vertices, faces, usable, noise)


def _auto(
    scan: ScanGeometry, surface: Surface, planes: list[PlaneCandidate], adjust: AlignmentAdjust
) -> tuple[FloatArray, tuple[str, ...]]:
    datums, issues = auto_datums(planes, surface)
    if datums:
        rows, _ = build_frame(datums, surface, require_point=False)
    else:
        rows = surface.principal_rows()
    rotation = adjustment_rotation(adjust) @ rows
    return rebased(make_transform(rotation, np.zeros(3)), scan.vertices, planes), issues


def auto_datums(
    planes: list[PlaneCandidate], surface: Surface
) -> tuple[list[Datum], tuple[str, ...]]:
    """Primary and secondary datum of the automatic alignment, and the fallback issue."""
    if not planes:
        return [], (IssueCode.PCA_FALLBACK,)
    primary = planes[0]
    z = -primary.normal
    primary_datum = Datum("plane", primary.point, z, "primary")
    side = [plane for plane in planes[1:] if abs(float(plane.normal @ z)) < PERPENDICULAR_SIN]
    if not side:
        return [primary_datum], (IssueCode.SINGLE_PLANE,)
    secondary = side[0]
    ties = [
        plane
        for plane in side[1:]
        if plane.area >= TIE_RATIO * secondary.area
        and float(plane.normal @ secondary.normal) < -0.9
    ]
    if ties:
        y = -secondary.normal + float(secondary.normal @ z) * z
        if surface.skew_sign(y / np.linalg.norm(y)) < 0:
            secondary = ties[0]
    return [primary_datum, Datum("plane", secondary.point, -secondary.normal, "secondary")], ()


def rebased(
    transform: FloatArray, vertices: FloatArray, planes: list[PlaneCandidate]
) -> FloatArray:
    """Move the origin to the bounding-box minimum; a plane lying there takes its place.

    Snapping onto planes makes the origin independent of scanner spikes below a face.
    """
    result = transform.copy()
    minimum = apply(transform, vertices).min(axis=0)
    rotation = transform[:3, :3]
    for axis in range(3):
        levels = [
            float(apply(transform, plane.point[None])[0, axis])
            for plane in planes
            if abs((rotation @ plane.normal)[axis]) > AXIS_ALIGNED_COS
        ]
        low = float(minimum[axis])
        near = [level for level in levels if low <= level <= low + ORIGIN_SNAP_MM]
        if near:
            minimum[axis] = min(near)
    result[:3, 3] -= minimum
    return result


def _faces_params(alignment: Alignment) -> FacesAlignmentParams:
    try:
        return from_json(alignment.params, FacesAlignmentParams)
    except KernelError as error:
        raise KernelError(ErrorCode.INVALID_PARAMS) from error


def _faces(
    document: Document,
    alignment: Alignment,
    scan: ScanGeometry,
    surface: Surface,
    job: JobContext,
) -> tuple[FloatArray, tuple[InputFit, ...]]:
    params = _faces_params(alignment)
    refs: list[tuple[InputRole, AlignmentInput]] = [
        ("primary", params.primary),
        ("secondary", params.secondary),
    ]
    if params.tertiary is not None:
        refs.append(("tertiary", params.tertiary))
    job.progress(None, ProgressStage.FITTING_INPUTS)
    datums: list[Datum] = []
    fits: list[InputFit] = []
    for role, ref in refs:
        job.check_cancelled()
        datum, fit = resolve_input(document, ref, role, scan, job)
        datums.append(_signed_axis(datum, surface))
        fits.append(fit)
    rows, origin = build_frame(datums, surface, require_point=params.tertiary is not None)
    rotation = adjustment_rotation(alignment.adjust) @ rows
    return make_transform(rotation, origin), tuple(fits)


def _signed_axis(datum: Datum, surface: Surface) -> Datum:
    """Fitted axes have no inherent sign; the skew rule gives them one."""
    if datum.kind != "axis":
        return datum
    direction = datum.direction * surface.skew_sign(datum.direction)
    return Datum("axis", datum.point, direction, datum.role)


def _largest_plane(transform: FloatArray, planes: list[PlaneCandidate]) -> LargestPlane | None:
    if not planes:
        return None
    normal = transform[:3, :3] @ planes[0].normal
    names: tuple[PrincipalPlane, ...] = ("YZ", "XZ", "XY")
    axis = int(np.argmax(np.abs(normal)))
    return LargestPlane(names[axis], line_angle_deg(normal, np.eye(3)[axis]))
