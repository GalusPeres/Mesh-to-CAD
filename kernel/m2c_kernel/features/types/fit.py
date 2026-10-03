"""Fit: a primitive fitted to scan triangles, used as construction geometry.

The feature keeps its triangles as a blob, so later changes of the source region
do not move it. Every rebuild refits them in part coordinates with the current
project tolerance, snap units and noise override; values the user fixed stay
fixed, design-intent snaps are re-derived (minus the rejected ones).

Statistics (`FeatureStatus.stats`) carry what the properties panel shows:
`noise`, `rms`, `maxDeviation`, `sigma`, `withinTolerance`, `tolerance`,
`faceCount`, `excludedFaces`, `concave` (1 hole, 0 boss); the fitted values
`radius`, `halfAngleDeg`, `majorRadius`, `minorRadius`, `offset`,
`pointX/Y/Z` (plane origin, axis point, apex or centre) and
`directionX/Y/Z` (normal or axis); and per applied snap `snap.<id>.value`,
`snap.<id>.measured`, `snap.<id>.uncertainty` plus `snap.direction.target`
(0, 1, 2 for X, Y, Z).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from m2c_kernel.codes.fit import ErrorCode, IssueCode
from m2c_kernel.document.results import Construction, DisplaySource, FeatureOutput, Issue
from m2c_kernel.features.common import StandardAxis, feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.api import (
    GLOBAL_AXES,
    AppliedSnap,
    Cone,
    Constraints,
    Cylinder,
    FitOutcome,
    FitRequest,
    Plane,
    Primitive,
    PrimitiveKind,
    SnapId,
    Sphere,
    Torus,
    primitive_patch,
    run_fit,
)
from m2c_kernel.geometry import FloatArray, Vec3, unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.model import DocumentSettings
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore


@dataclass(frozen=True, kw_only=True)
class FitFixed:
    """Parameters fixed by the user; every other parameter is computed by the fit.

    `direction` is the plane normal or the axis; `point` lies on the plane or the
    axis, or is the apex or the centre; `offset` is the plane's signed distance
    from the origin along its normal.
    """

    direction: Vec3 | None = None
    point: Vec3 | None = None
    radius: float | None = None
    half_angle_deg: float | None = None
    major_radius: float | None = None
    minor_radius: float | None = None
    offset: float | None = None


@dataclass(frozen=True, kw_only=True)
class FitRelation:
    """The direction is parallel or perpendicular to a global axis or another feature.

    Between a plane normal and an axis, parallel means perpendicular directions:
    a plane parallel to Z is vertical.
    """

    type: Literal["parallel", "perpendicular"]
    to: StandardAxis | str


@dataclass(frozen=True, kw_only=True)
class FitParams:
    faces: BlobRef
    source_region: str | None = None
    kind: PrimitiveKind
    robust: bool = False
    fixed: FitFixed = FitFixed()
    relation: FitRelation | None = None
    snap: bool = True
    rejected_snaps: list[SnapId] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class FitInput:
    """Like `FitParams`, but the triangles arrive as indices and are stored as a blob."""

    faces: U32Array
    source_region: str | None = None
    kind: PrimitiveKind
    robust: bool = False
    fixed: FitFixed = FitFixed()
    relation: FitRelation | None = None
    snap: bool = True
    rejected_snaps: list[SnapId] = field(default_factory=list)


def _store(value: FitInput, blobs: BlobStore) -> FitParams:
    return FitParams(
        faces=blobs.put(np.unique(value.faces).astype(np.uint32)),
        source_region=value.source_region,
        kind=value.kind,
        robust=value.robust,
        fixed=value.fixed,
        relation=value.relation,
        snap=value.snap,
        rejected_snaps=list(value.rejected_snaps),
    )


type Direction = tuple[FloatArray, bool]
"""A unit direction and whether it is a line (axis) rather than a plane normal."""


def construction_direction(construction: Construction) -> Direction | None:
    """The direction of a construction: a plane normal or an axis."""
    match construction.primitive:
        case Plane(normal=normal):
            return unit(normal), False
        case Cylinder(axis=axis) | Cone(axis=axis) | Torus(axis=axis):
            return unit(axis), True
    if construction.axis is not None:
        return unit(construction.axis.direction), True
    return None


_FIXED_BY_KIND: dict[PrimitiveKind, frozenset[str]] = {
    "plane": frozenset({"direction", "point", "offset"}),
    "sphere": frozenset({"point", "radius"}),
    "cylinder": frozenset({"direction", "point", "radius"}),
    "cone": frozenset({"direction", "point", "half_angle_deg"}),
    "torus": frozenset({"direction", "point", "major_radius", "minor_radius"}),
}


def _check_ranges(fixed: FitFixed) -> None:
    """Radii must be positive, half angles between 0 and 90 degrees, directions non-zero."""
    for name in ("radius", "major_radius", "minor_radius"):
        value = getattr(fixed, name)
        if value is not None and not value > 0.0:
            raise KernelError(ErrorCode.INVALID_VALUE, {"value": name})
    angle = fixed.half_angle_deg
    if angle is not None and not 0.0 < angle < 90.0:
        raise KernelError(ErrorCode.INVALID_VALUE, {"value": "half_angle_deg"})
    if fixed.direction is not None and not np.linalg.norm(fixed.direction) > 0.0:
        raise KernelError(ErrorCode.INVALID_VALUE, {"value": "direction"})


def build_constraints(
    kind: PrimitiveKind | Literal["auto"],
    fixed: FitFixed,
    relation: FitRelation | None,
    target: Direction | None,
) -> Constraints:
    """Constraints from the fixed values and the relation (validated against the kind)."""
    given = {name for name, value in vars(fixed).items() if value is not None}
    if kind != "auto" and not given <= _FIXED_BY_KIND[kind]:
        name = sorted(given - _FIXED_BY_KIND[kind])[0]
        raise KernelError(ErrorCode.FIXED_NOT_APPLICABLE, {"kind": kind, "value": name})
    if fixed.point is not None and fixed.offset is not None:
        raise KernelError(ErrorCode.FIXED_NOT_APPLICABLE, {"kind": kind, "value": "offset"})
    _check_ranges(fixed)
    direction = unit(fixed.direction) if fixed.direction is not None else None
    perpendicular = None
    if relation is not None:
        if kind == "sphere" or direction is not None or target is None:
            raise KernelError(ErrorCode.INVALID_RELATION, {"kind": kind})
        vector, target_is_line = target
        # Two lines or two normals: the relation applies to the directions as said.
        # A line and a plane normal: "parallel" means perpendicular directions.
        this_is_line = kind != "plane"
        if (relation.type == "parallel") == (target_is_line == this_is_line):
            direction = vector
        else:
            perpendicular = vector
    half_angle = None if fixed.half_angle_deg is None else float(np.radians(fixed.half_angle_deg))
    return Constraints(
        direction=direction,
        perpendicular_to=perpendicular,
        point=None if fixed.point is None else np.asarray(fixed.point, dtype=np.float64),
        radius=fixed.radius,
        half_angle=half_angle,
        major_radius=fixed.major_radius,
        minor_radius=fixed.minor_radius,
        offset=fixed.offset,
    )


def relation_target(
    relation: FitRelation | None, construction_of: Callable[[str], Construction]
) -> Direction | None:
    """Direction of the relation's target: a global axis or a feature's construction.

    `construction_of` maps a feature id to its `Construction` (`EvalContext.construction`).
    """
    if relation is None:
        return None
    for name, axis in GLOBAL_AXES.items():
        if relation.to == name:
            return axis, True
    direction = construction_direction(construction_of(relation.to))
    if direction is None:
        raise KernelError(ErrorCode.INVALID_RELATION, {"kind": "sphere"})
    return direction


def fit_request(
    kind: PrimitiveKind | Literal["auto"],
    robust: bool,
    constraints: Constraints,
    snap: bool,
    rejected: list[SnapId],
    settings: DocumentSettings,
) -> FitRequest:
    """The pipeline request for the given parameters and project settings."""
    return FitRequest(
        kind=kind,
        robust=robust,
        constraints=constraints,
        snap=snap,
        rejected=frozenset(rejected),
        tolerance=settings.tolerance,
        units=settings.snap_units,
        noise=settings.noise_override,
    )


def _primitive_values(primitive: Primitive) -> dict[str, float | None]:
    point, direction = _geometry(primitive)
    values: dict[str, float | None] = {
        f"point{axis}": float(value) for axis, value in zip("XYZ", point, strict=True)
    }
    if direction is not None:
        values |= {f"direction{axis}": float(v) for axis, v in zip("XYZ", direction, strict=True)}
    match primitive:
        case Plane(origin=origin, normal=normal):
            values["offset"] = float(np.dot(origin, normal))
        case Sphere(radius=radius) | Cylinder(radius=radius):
            values["radius"] = radius
        case Cone(half_angle=half_angle):
            values["halfAngleDeg"] = float(np.degrees(half_angle))
        case Torus(major_radius=major, minor_radius=minor):
            values["majorRadius"] = major
            values["minorRadius"] = minor
    return values


def _geometry(primitive: Primitive) -> tuple[Vec3, Vec3 | None]:
    match primitive:
        case Plane(origin=origin, normal=normal):
            return origin, normal
        case Cylinder(origin=origin, axis=axis):
            return origin, axis
        case Cone(apex=apex, axis=axis):
            return apex, axis
        case Sphere(center=center):
            return center, None
        case Torus(center=center, axis=axis):
            return center, axis


def _snap_values(snap: AppliedSnap) -> dict[str, float | None]:
    values: dict[str, float | None] = {
        f"snap.{snap.id}.value": snap.value,
        f"snap.{snap.id}.measured": snap.measured,
        f"snap.{snap.id}.uncertainty": snap.uncertainty,
    }
    if snap.target is not None:
        values[f"snap.{snap.id}.target"] = float("XYZ".index(snap.target))
    return values


def outcome_stats(outcome: FitOutcome) -> dict[str, float | None]:
    """The feature statistics listed in the module docstring."""
    stats = outcome.stats
    values: dict[str, float | None] = {
        "noise": stats.noise,
        "rms": stats.rms,
        "maxDeviation": stats.max_deviation,
        "sigma": stats.sigma,
        "withinTolerance": stats.within_tolerance,
        "tolerance": stats.tolerance,
        "faceCount": float(stats.face_count),
        "excludedFaces": float(stats.excluded_faces),
        "concave": None if stats.concave is None else float(stats.concave),
    }
    values |= _primitive_values(outcome.primitive)
    for snap in outcome.snaps:
        values |= _snap_values(snap)
    return values


def poor_fit_issue(outcome: FitOutcome) -> Issue:
    return Issue(
        IssueCode.POOR_FIT,
        {
            "share": round(outcome.stats.within_tolerance, 4),
            "tolerance": outcome.stats.tolerance,
        },
    )


def fit_display(outcome: FitOutcome) -> tuple[DisplaySource, ...]:
    patch = primitive_patch(outcome.primitive, outcome.used_points)
    return (
        DisplaySource(
            kind="mesh", style="construction", positions=patch.positions, indices=patch.faces
        ),
        DisplaySource(kind="lines", style="constructionEdges", positions=patch.outline),
    )


@feature_type(
    "fit",
    params=FitParams,
    input=FitInput,
    store=_store,
    reads=ReadSet(mesh=True, settings=("tolerance", "snap_units", "noise_override")),
)
class Fit:
    @staticmethod
    def references(params: FitParams) -> Refs:
        relation = params.relation
        return Refs(features=feature_refs(relation.to if relation else None))

    @staticmethod
    def evaluate(ctx: EvalContext, params: FitParams) -> FeatureOutput:
        target = relation_target(params.relation, ctx.construction)
        constraints = build_constraints(params.kind, params.fixed, params.relation, target)
        request = fit_request(
            params.kind,
            params.robust,
            constraints,
            params.snap,
            params.rejected_snaps,
            ctx.settings,
        )
        outcome = run_fit(
            ctx.mesh, ctx.face_set(params.faces), request, ctx.rng, ctx.job.check_cancelled
        )
        return FeatureOutput(
            construction=Construction(primitive=outcome.primitive),
            display=fit_display(outcome),
            stats=outcome_stats(outcome),
            issues=() if outcome.stats.passed else (poor_fit_issue(outcome),),
        )
