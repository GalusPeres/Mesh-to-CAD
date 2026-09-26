"""Display payloads for the renderer."""

from __future__ import annotations

from dataclasses import dataclass

from m2c_kernel.document.display import ScenePayload
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class FetchParams:
    keys: list[str]


@dataclass(frozen=True)
class FetchResult:
    payloads: list[ScenePayload]
    missing: list[str]
    """Keys that are no longer known (the renderer requests the current document again)."""


@command("scene.fetch")
def scene_fetch(ctx: JobContext, params: FetchParams) -> FetchResult:
    """Payloads for scene items the renderer does not have yet."""
    store = ctx.session.scene
    payloads: list[ScenePayload] = []
    missing: list[str] = []
    for key in params.keys:
        ctx.check_cancelled()
        payload = store.fetch(key)
        if payload is None:
            missing.append(key)
        else:
            payloads.append(payload)
    return FetchResult(payloads=payloads, missing=missing)
