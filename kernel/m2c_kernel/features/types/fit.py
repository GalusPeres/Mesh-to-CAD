"""Fit: a primitive fitted to scan triangles, used as construction geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from m2c_kernel.features.common import StandardAxis, feature_refs, not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.primitives import PrimitiveKind
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.wire import BlobRef, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput
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
        raise not_implemented("fit")
