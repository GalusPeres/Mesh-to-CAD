"""The complete fit of a triangle selection, shared by `fit.preview` and the fit feature.

Steps: points and jet normals of the selected triangles (synthetic triangles
from hole filling excluded) → type choice (`fit_best`) or the requested type,
with LO-RANSAC when `robust` → constrained refinement with the user's fixed
values and relation → design-intent snapping → statistics on all points and a
pass/fail state per triangle. The verdict rule is DESIGN.md 5.3: at least 95 %
of the used triangles lie within the project tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.fit import ErrorCode
from m2c_kernel.fitting.constrained import ConstrainedFit, Constraints, refine_constrained
from m2c_kernel.fitting.fit import FitError, fit_best, fit_primitive, robust_sigma
from m2c_kernel.fitting.intent import AppliedSnap, snap_fit
from m2c_kernel.fitting.primitives import Primitive, PrimitiveKind, signed_distance
from m2c_kernel.fitting.ransac import ransac
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.snapping import SnapUnits

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh

VERDICT_SHARE = 0.95
ROBUST_KINDS: tuple[PrimitiveKind, ...] = ("plane", "sphere", "cylinder", "cone")


class FaceState:
    """Values of the per-triangle pass/fail state (renderer `FACE_STATE`)."""

    NONE = 0
    PASS = 1
    FAIL = 2
    FAIL_FAR = 3


@dataclass(frozen=True)
class FitStats:
    """Quality of a fit. Distances in mm; shares in [0, 1]."""

    noise: float
    rms: float
    max_abs: float
    sigma: float
    inlier_ratio: float
    within_tolerance: float
    tolerance: float
    passed: bool
    face_count: int
    point_count: int


@dataclass(frozen=True)
class FitAlternative:
    kind: PrimitiveKind
    rms: float


@dataclass(frozen=True, kw_only=True)
class FitRequest:
    kind: PrimitiveKind | Literal["auto"] = "auto"
    robust: bool = False
    constraints: Constraints = field(default_factory=Constraints)
    direction_locked: bool = False
    snap: bool = True
    rejected: frozenset[str] = frozenset()
    tolerance: float = 0.1
    units: SnapUnits = "metric"
    noise: float | None = None


@dataclass(frozen=True)
class FitOutcome:
    primitive: Primitive
    stats: FitStats
    uncertainty: dict[str, float]
    alternatives: list[FitAlternative]
    snaps: list[AppliedSnap]
    face_states: npt.NDArray[np.uint8]
    """One state per requested face, aligned with the request."""
    used_faces: npt.NDArray[np.int64] = field(default_factory=lambda: np.zeros(0, np.int64))


def selection_points(
    mesh: EvalMesh, faces: npt.NDArray[np.integer]
) -> tuple[npt.NDArray[np.int64], FloatArray, FloatArray]:
    """Used faces (non-synthetic), their vertices and the jet normals of those vertices."""
    faces = np.asarray(faces, dtype=np.int64)
    faces = faces[(faces >= 0) & (faces < len(mesh.faces))]
    used = faces[~mesh.synthetic[faces]]
    if len(used) < MIN_FIT_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(used), "min": MIN_FIT_FACES})
    vertices = np.unique(mesh.faces[used].ravel())
    return used, mesh.vertices[vertices], mesh.jet.normals[vertices]


def _choose(
    request: FitRequest,
    points: FloatArray,
    normals: FloatArray,
    rng: np.random.Generator,
    noise: float | None,
) -> tuple[Primitive, npt.NDArray[np.bool_] | None, list[FitAlternative]]:
    """Start primitive, RANSAC inlier mask (robust only) and the alternatives list."""
    if request.robust:
        eps = 3.0 * noise if noise else request.tolerance
        kinds = ROBUST_KINDS if request.kind == "auto" else (request.kind,)
        results = []
        for kind in kinds:
            try:
                results.append(ransac(kind, points, normals, eps, rng))
            except FitError:
                continue
        if not results:
            raise KernelError(ErrorCode.DID_NOT_CONVERGE)
        # More parameters must collect clearly more inliers (order = fewest parameters first).
        best = results[0]
        for result in results[1:]:
            if result.inliers.sum() > 1.02 * best.inliers.sum():
                best = result
        alternatives = sorted(
            (FitAlternative(r.fit.kind, r.fit.rms) for r in results), key=lambda a: a.rms
        )
        return best.fit.primitive, best.inliers, alternatives
    if request.kind == "auto":
        winner, trials = fit_best(points, normals, rng, noise=noise)
        alternatives = [FitAlternative(trial.kind, trial.rms) for trial in trials]
        return winner.primitive, None, alternatives
    fit = fit_primitive(request.kind, points, normals, rng)
    return fit.primitive, None, [FitAlternative(fit.kind, fit.rms)]


def run_fit(
    mesh: EvalMesh,
    faces: npt.NDArray[np.integer],
    request: FitRequest,
    rng: np.random.Generator,
) -> FitOutcome:
    """Fit, snap and evaluate a triangle selection (see module docstring)."""
    used, points, normals = selection_points(mesh, faces)
    try:
        start, inliers, alternatives = _choose(request, points, normals, rng, request.noise)
        fit_points = points if inliers is None else points[inliers]
        base: ConstrainedFit = refine_constrained(start, fit_points, request.constraints, rng)
        final, snaps = base, []
        if request.snap:
            snapped = snap_fit(
                base,
                fit_points,
                request.constraints,
                rng,
                units=request.units,
                direction_locked=request.direction_locked,
                rejected=request.rejected,
            )
            final, snaps = snapped.fit, snapped.snaps
    except (FitError, np.linalg.LinAlgError, ValueError) as error:
        if isinstance(error, KernelError):
            raise
        raise KernelError(ErrorCode.DID_NOT_CONVERGE, details=str(error)) from error

    distances = signed_distance(final.primitive, points)
    sigma = robust_sigma(distances if inliers is None else distances[inliers])
    noise = request.noise if request.noise is not None else sigma
    tolerance = request.tolerance
    face_distance = np.abs(signed_distance(final.primitive, mesh.face_centroids[used]))
    within = float(np.mean(face_distance <= tolerance))
    used_states = np.where(
        face_distance <= tolerance,
        FaceState.PASS,
        np.where(face_distance <= 3 * tolerance, FaceState.FAIL, FaceState.FAIL_FAR),
    ).astype(np.uint8)
    requested = np.asarray(faces, dtype=np.int64)
    all_states = np.zeros(len(mesh.faces), dtype=np.uint8)
    all_states[used] = used_states
    valid = (requested >= 0) & (requested < len(mesh.faces))
    states = np.where(valid, all_states[np.where(valid, requested, 0)], 0).astype(np.uint8)
    inlier_ratio = (
        float(inliers.mean())
        if inliers is not None
        else float(np.mean(np.abs(distances) <= 3.0 * max(sigma, 1e-4)))
    )
    stats = FitStats(
        noise=float(noise),
        rms=float(np.sqrt(np.mean(distances * distances))),
        max_abs=float(np.abs(distances).max()),
        sigma=float(sigma),
        inlier_ratio=inlier_ratio,
        within_tolerance=within,
        tolerance=float(tolerance),
        passed=within >= VERDICT_SHARE,
        face_count=len(used),
        point_count=len(points),
    )
    return FitOutcome(
        primitive=final.primitive,
        stats=stats,
        uncertainty=base.uncertainty,
        alternatives=alternatives,
        snaps=snaps,
        face_states=states,
        used_faces=used,
    )
