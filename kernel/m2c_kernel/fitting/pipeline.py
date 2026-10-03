"""The complete fit of a triangle selection, shared by `fit.preview` and the fit feature.

Steps: points and jet normals of the selected triangles (synthetic triangles
from hole filling excluded) -> type choice (`fit_best`) or the requested type,
with LO-RANSAC when `robust` -> refinement with the user's fixed values and
relation -> design-intent snapping -> statistics on all used points and a
pass/fail state per triangle.

The verdict rule is DESIGN.md 5.3: at least 95 % of the used triangles lie
within the project tolerance (distance of the triangle centroid). With the
robust option the used triangles are the consensus set of RANSAC; the other
selected triangles are still coloured, so the user sees what was left out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.fit import ErrorCode
from m2c_kernel.fitting.constrained import ConstrainedFit, Constraints, refine_constrained
from m2c_kernel.fitting.fit import FitError, fit_primitive, robust_sigma, trial_fits
from m2c_kernel.fitting.intent import AppliedSnap, snap_fit
from m2c_kernel.fitting.primitives import (
    PRIMITIVE_KINDS,
    Plane,
    Primitive,
    PrimitiveKind,
    signed_distance,
    surface_normals,
)
from m2c_kernel.fitting.ransac import RansacResult, ransac
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import DEFAULT_TOLERANCE_MM, MIN_FIT_FACES
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.snapping import SnapUnits

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh

VERDICT_SHARE = 0.95
FAR_FACTOR = 3.0
"""Triangles beyond this many tolerances are drawn in the dark fail colour."""

ROBUST_EPS_FACTOR = 3.0
"""RANSAC inlier distance in multiples of the scan noise, at most the project tolerance."""

MIN_ROBUST_EPS_MM = 0.01
ROBUST_AUTO_KINDS: tuple[PrimitiveKind, ...] = ("plane", "sphere", "cylinder", "cone")
ROBUST_WIN_FACTOR = 1.02
"""A robust type with more parameters must collect this many times the inliers to win."""

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]


class FaceState:
    """Values of the per-triangle pass/fail state (renderer `FACE_STATE`)."""

    NONE = 0
    PASS = 1
    FAIL = 2
    FAIL_FAR = 3


@dataclass(frozen=True, kw_only=True)
class FitStats:
    """Quality of a fit. Distances in mm, shares in [0, 1].

    `noise` is the scan noise (project override or estimate); `sigma` the robust
    standard deviation of this fit's residuals. `within_tolerance` is the share
    of used triangles within `tolerance`; `passed` applies the 95 % rule.
    `excluded_faces` counts selected triangles the fit did not use (synthetic
    triangles, robust outliers). `uncertainty` holds the standard uncertainty of
    each computed parameter (mm; degrees for `direction` and `halfAngle`).
    `concave` tells a hole from a boss (curved kinds only).
    """

    noise: float
    rms: float
    max_deviation: float
    sigma: float
    inlier_ratio: float
    within_tolerance: float
    tolerance: float
    passed: bool
    face_count: int
    excluded_faces: int
    point_count: int
    uncertainty: dict[str, float]
    concave: bool | None


@dataclass(frozen=True, kw_only=True)
class FitAlternative:
    """Another primitive type and its RMS over the same points, for the type selector."""

    kind: PrimitiveKind
    rms: float


@dataclass(frozen=True, kw_only=True)
class FitRequest:
    kind: PrimitiveKind | Literal["auto"] = "auto"
    robust: bool = False
    constraints: Constraints = field(default_factory=Constraints)
    snap: bool = True
    rejected: frozenset[str] = frozenset()
    tolerance: float = DEFAULT_TOLERANCE_MM
    units: SnapUnits = "metric"
    noise: float | None = None
    """Scan noise; None uses the estimate of the jet fit."""


@dataclass(frozen=True)
class FitOutcome:
    primitive: Primitive
    stats: FitStats
    alternatives: list[FitAlternative]
    snaps: list[AppliedSnap]
    face_states: npt.NDArray[np.uint8]
    """One state per requested face, in request order."""
    used_faces: IntArray
    used_points: FloatArray


@dataclass(frozen=True)
class _Selection:
    faces: IntArray
    """Non-synthetic selected faces."""
    corners: IntArray
    """(faces, 3) indices into `points`."""
    points: FloatArray
    normals: FloatArray
    excluded: int


def applicable_kinds(constraints: Constraints) -> tuple[PrimitiveKind, ...]:
    """Primitive kinds that can honour all given constraints."""
    kinds = list(PRIMITIVE_KINDS)
    if constraints.direction is not None or constraints.perpendicular_to is not None:
        kinds.remove("sphere")
    if constraints.offset is not None:
        kinds = [kind for kind in kinds if kind == "plane"]
    if constraints.radius is not None:
        kinds = [kind for kind in kinds if kind in ("sphere", "cylinder")]
    if constraints.half_angle is not None:
        kinds = [kind for kind in kinds if kind == "cone"]
    if constraints.major_radius is not None or constraints.minor_radius is not None:
        kinds = [kind for kind in kinds if kind == "torus"]
    return tuple(kinds)


def _selection(mesh: EvalMesh, faces: npt.ArrayLike) -> _Selection:
    requested = np.asarray(faces, dtype=np.int64).reshape(-1)
    valid = requested[(requested >= 0) & (requested < len(mesh.faces))]
    valid = np.unique(valid)
    used = valid[~mesh.synthetic[valid]]
    if len(used) < MIN_FIT_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(used), "min": MIN_FIT_FACES})
    vertices, corners = np.unique(mesh.faces[used].ravel(), return_inverse=True)
    return _Selection(
        faces=used,
        corners=corners.reshape(-1, 3).astype(np.int64),
        points=mesh.vertices[vertices],
        normals=mesh.jet.normals[vertices],
        excluded=len(valid) - len(used),
    )


@dataclass(frozen=True)
class _Start:
    primitive: Primitive
    inliers: BoolArray | None
    alternatives: list[FitAlternative]


def _alternatives(trials: list[Primitive], points: FloatArray) -> list[FitAlternative]:
    result = []
    for trial in trials:
        d = signed_distance(trial, points)
        result.append(FitAlternative(kind=trial.type, rms=float(np.sqrt(np.mean(d * d)))))
    return sorted(result, key=lambda alternative: alternative.rms)


def _robust_start(
    request: FitRequest,
    kinds: tuple[PrimitiveKind, ...],
    selection: _Selection,
    noise: float,
    rng: np.random.Generator,
    check_cancelled: Callable[[], None] | None,
) -> _Start:
    eps = max(min(ROBUST_EPS_FACTOR * noise, request.tolerance), MIN_ROBUST_EPS_MM)
    candidates = kinds if request.kind == "auto" else (request.kind,)
    if request.kind == "auto":
        candidates = tuple(kind for kind in candidates if kind in ROBUST_AUTO_KINDS)
    results: list[RansacResult] = []
    for kind in candidates:
        try:
            results.append(
                ransac(
                    kind,
                    selection.points,
                    selection.normals,
                    eps,
                    rng,
                    check_cancelled=check_cancelled,
                )
            )
        except FitError:
            continue
    if not results:
        raise KernelError(ErrorCode.DID_NOT_CONVERGE)
    # Kinds are ordered by parameter count; a richer kind must explain clearly more points.
    best = results[0]
    for result in results[1:]:
        if result.inliers.sum() > ROBUST_WIN_FACTOR * best.inliers.sum():
            best = result
    alternatives = sorted(
        (
            FitAlternative(kind=result.fit.kind, rms=_rms(result.fit.primitive, selection, result))
            for result in results
        ),
        key=lambda alternative: alternative.rms,
    )
    return _Start(best.fit.primitive, best.inliers, alternatives)


def _rms(primitive: Primitive, selection: _Selection, result: RansacResult) -> float:
    d = signed_distance(primitive, selection.points[result.inliers])
    return float(np.sqrt(np.mean(d * d)))


def _start(
    request: FitRequest,
    selection: _Selection,
    noise: float,
    rng: np.random.Generator,
    check_cancelled: Callable[[], None] | None,
) -> _Start:
    kinds = applicable_kinds(request.constraints)
    if request.kind != "auto" and request.kind not in kinds:
        raise KernelError(ErrorCode.FIXED_NOT_APPLICABLE, {"kind": request.kind})
    if not kinds:
        raise KernelError(ErrorCode.FIXED_NOT_APPLICABLE, {"kind": request.kind})
    if request.robust:
        return _robust_start(request, kinds, selection, noise, rng, check_cancelled)
    points, normals = selection.points, selection.normals
    preferred, trials = trial_fits(points, normals, rng, noise=noise, kinds=kinds)
    kind = preferred.kind if request.kind == "auto" and preferred else request.kind
    if kind == "auto":
        raise KernelError(ErrorCode.DID_NOT_CONVERGE)
    winner = fit_primitive(kind, points, normals, rng).primitive
    others = [trial.primitive for trial in trials if trial.kind != kind]
    return _Start(winner, None, _alternatives([winner, *others], points))


def _concave(primitive: Primitive, points: FloatArray, normals: FloatArray) -> bool | None:
    """Whether the scan's outward normals point towards the axis or centre (a hole)."""
    if isinstance(primitive, Plane):
        return None
    agreement = np.einsum("ij,ij->i", surface_normals(primitive, points), normals)
    return bool(np.mean(agreement) < 0)


def run_fit(
    mesh: EvalMesh,
    faces: npt.ArrayLike,
    request: FitRequest,
    rng: np.random.Generator,
    check_cancelled: Callable[[], None] | None = None,
) -> FitOutcome:
    """Fit, snap and evaluate a triangle selection (module docstring)."""
    selection = _selection(mesh, faces)
    noise = request.noise if request.noise is not None else mesh.jet.noise
    try:
        start = _start(request, selection, noise, rng, check_cancelled)
        inliers = start.inliers
        fit_points = selection.points if inliers is None else selection.points[inliers]
        constraints = request.constraints
        # A free fit is already refined; only its uncertainties are needed.
        final: ConstrainedFit = refine_constrained(
            start.primitive, fit_points, constraints, rng, solve=not constraints.empty
        )
        snaps: list[AppliedSnap] = []
        if request.snap:
            snapped = snap_fit(
                final,
                fit_points,
                constraints,
                rng,
                units=request.units,
                rejected=request.rejected,
            )
            final, snaps = snapped.fit, snapped.snaps
    except FitError as error:
        raise KernelError(ErrorCode.DID_NOT_CONVERGE, details=str(error)) from error
    except (np.linalg.LinAlgError, ValueError) as error:
        raise KernelError(ErrorCode.DID_NOT_CONVERGE, details=repr(error)) from error

    primitive = final.primitive
    distances = signed_distance(primitive, fit_points)
    sigma = robust_sigma(distances)

    counted = np.ones(len(selection.faces), dtype=bool)
    if inliers is not None:
        # A triangle belongs to the consensus set when most of its corners do.
        counted = inliers[selection.corners].sum(axis=1) >= 2
    face_distance = np.abs(signed_distance(primitive, mesh.face_centroids[selection.faces]))
    tolerance = request.tolerance
    states = np.full(len(selection.faces), FaceState.FAIL_FAR, dtype=np.uint8)
    states[face_distance <= FAR_FACTOR * tolerance] = FaceState.FAIL
    states[face_distance <= tolerance] = FaceState.PASS
    within = float(np.mean(face_distance[counted] <= tolerance)) if counted.any() else 0.0

    if inliers is not None:
        inlier_ratio = float(inliers.mean())
    else:
        inlier_ratio = float(np.mean(np.abs(distances) <= 3.0 * max(sigma, 1e-4)))
    fit_normals = selection.normals if inliers is None else selection.normals[inliers]
    stats = FitStats(
        noise=float(noise),
        rms=float(np.sqrt(np.mean(distances * distances))),
        max_deviation=float(np.abs(distances).max()),
        sigma=float(sigma),
        inlier_ratio=inlier_ratio,
        within_tolerance=within,
        tolerance=float(tolerance),
        passed=within >= VERDICT_SHARE,
        face_count=int(counted.sum()),
        excluded_faces=selection.excluded + int((~counted).sum()),
        point_count=len(fit_points),
        uncertainty=final.uncertainty,
        concave=_concave(primitive, fit_points, fit_normals),
    )
    return FitOutcome(
        primitive=primitive,
        stats=stats,
        alternatives=_final_alternatives(start.alternatives, primitive, stats.rms),
        snaps=snaps,
        face_states=_request_states(mesh, faces, selection.faces, states),
        used_faces=selection.faces[counted],
        used_points=fit_points,
    )


def _final_alternatives(
    alternatives: list[FitAlternative], primitive: Primitive, rms: float
) -> list[FitAlternative]:
    """The chosen kind with its final RMS, the others with their trial RMS, best first."""
    others = [item for item in alternatives if item.kind != primitive.type]
    chosen = FitAlternative(kind=primitive.type, rms=rms)
    return sorted([chosen, *others], key=lambda alternative: alternative.rms)


def _request_states(
    mesh: EvalMesh, faces: npt.ArrayLike, used: IntArray, states: npt.NDArray[np.uint8]
) -> npt.NDArray[np.uint8]:
    per_face = np.zeros(len(mesh.faces), dtype=np.uint8)
    per_face[used] = states
    requested = np.asarray(faces, dtype=np.int64).reshape(-1)
    valid = (requested >= 0) & (requested < len(mesh.faces))
    result: npt.NDArray[np.uint8] = np.where(valid, per_face[np.where(valid, requested, 0)], 0)
    return result.astype(np.uint8)
