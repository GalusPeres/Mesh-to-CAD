"""Automatic freeform surfacing.

An `autoSurface` feature is previewed with `surfacing.preview` instead of `doc.preview`:
fitting a large scan takes from seconds to a few minutes, so it runs as an exclusive job
(other tools get `kernel.busy` instead of queueing behind it, and the status bar shows
its progress). The evaluation is the same as `doc.preview` and is cached by result key,
so committing the same operations with `doc.apply` afterwards is immediate.
"""

from __future__ import annotations

from dataclasses import dataclass

from m2c_kernel.codes.surfacing import ErrorCode
from m2c_kernel.commands.doc import PreviewParams as DocPreviewParams
from m2c_kernel.commands.doc import PreviewResult, doc_preview
from m2c_kernel.document.ops import AddFeature, DocOp, UpdateFeature
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext

AUTO_SURFACE = "autoSurface"


@dataclass(frozen=True)
class PreviewParams:
    base_revision: int
    ops: list[DocOp]


@command("surfacing.preview", lane=True, exclusive=True)
def surfacing_preview(ctx: JobContext, params: PreviewParams) -> PreviewResult:
    """Evaluate one added or changed `autoSurface` feature as an exclusive job.

    `ops` must be a single `addFeature` of type `autoSurface` or a single
    `updateFeature` of an existing `autoSurface` feature; anything else fails with
    `surfacing.notAutoSurface`.
    """
    if len(params.ops) != 1 or not _targets_auto_surface(ctx, params.ops[0]):
        raise KernelError(ErrorCode.NOT_AUTO_SURFACE)
    return doc_preview(ctx, DocPreviewParams(base_revision=params.base_revision, ops=params.ops))


def _targets_auto_surface(ctx: JobContext, op: DocOp) -> bool:
    match op:
        case AddFeature(feature=feature):
            return feature.type == AUTO_SURFACE
        case UpdateFeature(id=feature_id):
            existing = ctx.session.document.feature(feature_id)
            return existing is not None and existing.type == AUTO_SURFACE
    return False
