"""Reading, changing, previewing and navigating the document."""

from __future__ import annotations

from dataclasses import dataclass

from m2c_kernel.codes.document import ErrorCode
from m2c_kernel.document.display import SceneItem, register_body, register_sources
from m2c_kernel.document.ops import DocOp, apply_ops, dependents
from m2c_kernel.document.rebuild import rebuild
from m2c_kernel.document.results import BodyInfo, FeatureStatus
from m2c_kernel.document.snapshot import DocumentSnapshot
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class GetParams:
    pass


@command("doc.get")
def doc_get(ctx: JobContext, params: GetParams) -> DocumentSnapshot:
    """The current document with status and scene (after startup or a kernel restart)."""
    return ctx.session.snapshot("current", ctx)


@dataclass(frozen=True)
class ApplyParams:
    base_revision: int
    ops: list[DocOp]
    label: str


@dataclass(frozen=True)
class ApplyResult:
    revision: int


@command("doc.apply")
def doc_apply(ctx: JobContext, params: ApplyParams) -> ApplyResult:
    """Apply operations as one new revision; fails if the base is not the head."""
    session = ctx.session
    _require_head(session.document.revision, params.base_revision)
    applied = apply_ops(session.document, params.ops, session.feature_types, session.blobs)
    snapshot = session.commit(applied.document, params.label, ctx)
    return ApplyResult(revision=snapshot.revision)


@dataclass(frozen=True)
class PreviewParams:
    base_revision: int
    ops: list[DocOp]


@dataclass(frozen=True)
class PreviewResult:
    """Result of evaluating the document with the operations applied, without committing.

    Evaluation stops after the last added or changed feature (`feature_id`);
    `items` draw what that feature produces.
    """

    feature_id: str | None
    status: FeatureStatus | None
    items: tuple[SceneItem, ...]
    bodies: tuple[BodyInfo, ...]
    result_key: str | None = None
    """Result key of the previewed feature (for `inspection.previewDeviation`)."""


@command("doc.preview", lane=True)
def doc_preview(ctx: JobContext, params: PreviewParams) -> PreviewResult:
    """Evaluate a tool's pending change. Results are cached, so the commit reuses them."""
    session = ctx.session
    _require_head(session.document.revision, params.base_revision)
    applied = apply_ops(session.document, params.ops, session.feature_types, session.blobs)
    target = applied.touched[-1] if applied.touched else None
    result = rebuild(applied.document, session.environment(), ctx, stop_after=target)
    if target is None:
        return PreviewResult(feature_id=None, status=None, items=(), bodies=())

    items: list[SceneItem] = []
    bodies: list[BodyInfo] = []
    output = result.outputs.get(target)
    if output is not None:
        for body_id, body in output.bodies.changed.items():
            key = result.body_keys[body_id]
            items += register_body(body_id, body, key, target, session.scene, "previewBody")
            check = result.body_checks[body_id]
            bodies.append(
                BodyInfo(
                    id=body_id,
                    owner=target,
                    valid=check.valid,
                    solids=check.solids,
                    volume=check.volume,
                    area=check.area,
                    max_tolerance=check.max_tolerance,
                    face_tags=body.face_tags,
                )
            )
        items += register_sources(target, result.result_keys[target], output.display, session.scene)
    return PreviewResult(
        feature_id=target,
        status=result.statuses.get(target),
        items=tuple(items),
        bodies=tuple(bodies),
        result_key=result.result_keys.get(target),
    )


@dataclass(frozen=True)
class CheckoutParams:
    revision: int


@dataclass(frozen=True)
class CheckoutResult:
    revision: int


@command("doc.checkout")
def doc_checkout(ctx: JobContext, params: CheckoutParams) -> CheckoutResult:
    """Move the head to another revision (undo and redo)."""
    snapshot = ctx.session.checkout(params.revision, ctx)
    return CheckoutResult(revision=snapshot.revision)


@dataclass(frozen=True)
class DependentsParams:
    feature_id: str


@dataclass(frozen=True)
class DependentsResult:
    feature_ids: list[str]


@command("doc.dependents")
def doc_dependents(ctx: JobContext, params: DependentsParams) -> DependentsResult:
    """Features that would be deleted together with the given one."""
    session = ctx.session
    if session.document.feature(params.feature_id) is None:
        raise KernelError(ErrorCode.UNKNOWN_FEATURE, {"feature": params.feature_id})
    ids = dependents(session.document, params.feature_id, session.feature_types)
    return DependentsResult(feature_ids=ids)


def _require_head(head: int, base: int) -> None:
    if head != base:
        raise KernelError(ErrorCode.STALE_REVISION, {"head": head, "base": base})
