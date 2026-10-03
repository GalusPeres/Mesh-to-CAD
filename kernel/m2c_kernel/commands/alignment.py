"""Scan alignment: preview of a pending alignment.

Committing goes through `doc.apply` with `setAlignment`, using the `params` this
preview returns (a working selection is stored as a face set there).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from m2c_kernel.alignment.api import InputFit, LargestPlane, evaluate
from m2c_kernel.alignment.params import (
    AlignmentInput,
    FacesAlignmentParams,
    FacesInput,
    FeatureInput,
    RegionInput,
)
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.document.model import Alignment, AlignmentAdjust
from m2c_kernel.geometry import Matrix4
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import JsonValue, U32Array, to_json
from m2c_kernel.session.blobs import BlobStore
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True, kw_only=True)
class SelectionInput:
    """The working selection; the preview stores it as a face set."""

    type: Literal["selection"] = "selection"
    faces: U32Array


type AlignmentSlot = FeatureInput | RegionInput | FacesInput | SelectionInput


@dataclass(frozen=True, kw_only=True)
class AlignmentPreviewParams:
    method: Literal["none", "auto", "faces"]
    primary: AlignmentSlot | None = None
    secondary: AlignmentSlot | None = None
    tertiary: AlignmentSlot | None = None
    adjust: AlignmentAdjust = field(default_factory=AlignmentAdjust)


@dataclass(frozen=True)
class AlignmentPreviewResult:
    matrix: Matrix4
    """Scan-to-part transform, row-major."""
    params: JsonValue
    """Parameters for `setAlignment`, with a selection input stored as a face set."""
    inputs: list[InputFit]
    largest_plane: LargestPlane | None
    plane_count: int
    issues: list[str]


@command("alignment.preview", lane=True)
def alignment_preview(ctx: JobContext, params: AlignmentPreviewParams) -> AlignmentPreviewResult:
    """Evaluate an alignment without committing it: matrix, input fits, remaining tilt."""
    session = ctx.session
    stored: JsonValue = None
    if params.method == "faces":
        stored = to_json(_stored_params(params, session.blobs), FacesAlignmentParams)
    alignment = Alignment(method=params.method, params=stored, adjust=params.adjust)
    result = evaluate(session.document, alignment, ctx)
    return AlignmentPreviewResult(
        matrix=result.matrix,
        params=stored,
        inputs=list(result.inputs),
        largest_plane=result.largest_plane,
        plane_count=result.plane_count,
        issues=list(result.issues),
    )


def _stored_params(params: AlignmentPreviewParams, blobs: BlobStore) -> FacesAlignmentParams:
    if params.primary is None or params.secondary is None:
        raise KernelError(ErrorCode.INVALID_PARAMS)
    return FacesAlignmentParams(
        primary=_stored(params.primary, blobs),
        secondary=_stored(params.secondary, blobs),
        tertiary=_stored(params.tertiary, blobs) if params.tertiary is not None else None,
    )


def _stored(slot: AlignmentSlot, blobs: BlobStore) -> AlignmentInput:
    if isinstance(slot, SelectionInput):
        return FacesInput(faces=blobs.put(np.unique(slot.faces).astype(np.uint32)))
    return slot
