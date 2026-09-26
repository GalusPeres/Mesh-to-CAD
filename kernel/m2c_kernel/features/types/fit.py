"""Fit: a primitive fitted to scan triangles, used as construction geometry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from m2c_kernel.codes.fit import ErrorCode, IssueCode
from m2c_kernel.document.results import Construction, FeatureOutput, Issue
from m2c_kernel.features.common import StandardAxis, feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.constrained import Constraints
from m2c_kernel.fitting.display import construction_display
from m2c_kernel.fitting.pipeline import FitOutcome, FitRequest, run_fit
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, PrimitiveKind, Torus
from m2c_kernel.geometry import FloatArray, Vec3, unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore


@dataclass(frozen=True, kw_only=True)
class FitFixed:
    """Parameters fixed by the user; every other parameter is computed by the fit."""

    direction: Vec3 | None = None
    point: Vec3 | None = None
    radius: float | None = None
    half_angle_deg: float | None = None
    major_radius: float | None = None
    minor_radius: float | None = None
    offset: float | None = None


@dataclass(frozen=True, kw_only=True)
class FitRelation:
    type: Literal["parallel", "perpendicular"]
    to: StandardAxis | str
    """A global axis or the id of a feature with a direction."""


@dataclass(frozen=True, kw_only=True)
class FitParams:
    faces: BlobRef
    source_region: str | None = None
    kind: PrimitiveKind
    robust: bool = False
    fixed: FitFixed = FitFixed()
    relation: FitRelation | None = None
    snap: bool = True
    rejected_snaps: list[str] = field(default_factory=list)


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
    rejected_snaps: list[str] = field(default_factory=list)


def _store(value: FitInput, blobs: BlobStore) -> FitParams:
    return FitParams(
        faces=blobs.put(np.sort(value.faces).astype(np.uint32)),
        source_region=value.source_region,
        kind=value.kind,
        robust=value.robust,
        fixed=value.fixed,
        relation=value.relation,
        snap=value.snap,
        rejected_snaps=list(value.rejected_snaps),
    )


GLOBAL_AXES: dict[str, Vec3] = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def construction_direction(construction: Construction) -> tuple[FloatArray, bool] | None:
    """Direction of a construction and whether it is a line (axis) rather than a plane normal."""
    match construction.primitive:
        case Plane(normal=normal):
            return unit(normal), False
        case Cylinder(axis=axis) | Cone(axis=axis) | Torus(axis=axis):
            return unit(axis), True
    if construction.axis is not None:
        return unit(construction.axis.direction), True
    return None


def build_constraints(
    kind: PrimitiveKind,
    fixed: FitFixed,
    relation: FitRelation | None,
    target: tuple[FloatArray, bool] | None,
) -> tuple[Constraints, bool]:
    """Constraints of the fixed values and the relation; also whether the direction is locked.

    A relation between two lines or two plane normals means what it says; between
    a line and a plane normal, parallel means perpendicular directions.
    """
    if kind == "sphere" and (relation is not None or fixed.direction is not None):
        raise KernelError(ErrorCode.INVALID_RELATION, {"kind": kind})
    direction = unit(fixed.direction) if fixed.direction is not None else None
    perpendicular = None
    if relation is not None and direction is None:
        if target is None:
            raise KernelError(ErrorCode.INVALID_RELATION, {"kind": kind})
        vector, target_is_line = target
        same_kind = target_is_line == (kind != "plane")
        if (relation.type == "parallel") == same_kind:
            direction = vector
        else:
            perpendicular = vector
    half_angle = np.radians(fixed.half_angle_deg) if fixed.half_angle_deg is not None else None
    constraints = Constraints(
        direction=direction,
        perpendicular_to=perpendicular,
        point=np.asarray(fixed.point, dtype=np.float64) if fixed.point is not None else None,
        radius=fixed.radius,
        half_angle=float(half_angle) if half_angle is not None else None,
        major_radius=fixed.major_radius,
        minor_radius=fixed.minor_radius,
        offset=fixed.offset,
    )
    return constraints, direction is not None or perpendicular is not None


def relation_target(
    relation: FitRelation | None, construction_of: Callable[[str], Construction]
) -> tuple[FloatArray, bool] | None:
    """Resolve a relation's target: a global axis or a feature's construction."""
    if relation is None:
        return None
    if relation.to in GLOBAL_AXES:
        return np.asarray(GLOBAL_AXES[relation.to]), True
    return construction_direction(construction_of(relation.to))


def outcome_stats(outcome: FitOutcome) -> dict[str, float | None]:
    """Feature statistics; keys are i18n keys of the properties panel."""
    stats = outcome.stats
    values: dict[str, float | None] = {
        "fit.stats.noise": stats.noise,
        "fit.stats.rms": stats.rms,
        "fit.stats.max": stats.max_abs,
        "fit.stats.withinTolerance": stats.within_tolerance,
        "fit.stats.faces": float(stats.face_count),
    }
    for snap in outcome.snaps:
        values[f"fit.snaps.{snap.id}"] = snap.value
    return values


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
        constraints, locked = build_constraints(params.kind, params.fixed, params.relation, target)
        settings = ctx.settings
        request = FitRequest(
            kind=params.kind,
            robust=params.robust,
            constraints=constraints,
            direction_locked=locked,
            snap=params.snap,
            rejected=frozenset(params.rejected_snaps),
            tolerance=settings.tolerance,
            units=settings.snap_units,
            noise=settings.noise_override,
        )
        outcome = run_fit(ctx.mesh, ctx.face_set(params.faces), request, ctx.rng)
        points = ctx.mesh.vertices[np.unique(ctx.mesh.faces[outcome.used_faces].ravel())]
        issues: tuple[Issue, ...] = ()
        if not outcome.stats.passed:
            issues = (
                Issue(
                    IssueCode.POOR_FIT,
                    {
                        "share": round(outcome.stats.within_tolerance * 100, 1),
                        "tolerance": outcome.stats.tolerance,
                    },
                ),
            )
        return FeatureOutput(
            construction=Construction(primitive=outcome.primitive),
            display=construction_display(outcome.primitive, points),
            stats=outcome_stats(outcome),
            issues=issues,
        )
