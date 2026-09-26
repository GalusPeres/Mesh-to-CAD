"""Freeform patch: a B-spline surface fitted to scan triangles (height field)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.features.common import not_implemented
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.protocol.wire import BlobRef, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput
    from m2c_kernel.session.blobs import BlobStore


@dataclass(frozen=True, kw_only=True)
class FreeformPatchParams:
    faces: BlobRef
    source_region: str | None = None
    spans: tuple[int, int] | None = None
    """B-spline spans (u, v); None chooses them from the patch size."""
    smoothing: float = 1e-4
    margin: float = 2.0


@dataclass(frozen=True, kw_only=True)
class FreeformPatchInput:
    faces: U32Array
    source_region: str | None = None
    spans: tuple[int, int] | None = None
    smoothing: float = 1e-4
    margin: float = 2.0


def _store(value: FreeformPatchInput, blobs: BlobStore) -> FreeformPatchParams:
    return FreeformPatchParams(
        faces=blobs.put(np.sort(value.faces).astype(np.uint32)),
        source_region=value.source_region,
        spans=value.spans,
        smoothing=value.smoothing,
        margin=value.margin,
    )


@feature_type(
    "freeformPatch",
    params=FreeformPatchParams,
    input=FreeformPatchInput,
    store=_store,
    reads=ReadSet(mesh=True),
)
class FreeformPatch:
    @staticmethod
    def references(params: FreeformPatchParams) -> Refs:
        return Refs()

    @staticmethod
    def evaluate(ctx: EvalContext, params: FreeformPatchParams) -> FeatureOutput:
        raise not_implemented("freeformPatch")
