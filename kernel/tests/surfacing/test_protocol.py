"""Auto surfaces through the protocol, as the tool panel calls them."""

from __future__ import annotations

import queue
from pathlib import Path

import pytest

from m2c_kernel.codes.surfacing import ProgressStage
from tests.kernel_process import KernelProcess
from tests.surfacing import shapes
from tests.synthetic import write_binary_stl

pytestmark = pytest.mark.occt


def test_preview_with_progress_and_commit(kernel: KernelProcess, tmp_path: Path) -> None:
    scan = shapes.blob()
    path = write_binary_stl(tmp_path / "blob.stl", scan.vertices, scan.faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok
    head = kernel.call("doc.get").result

    feature = {"type": "autoSurface", "params": {"detail": "coarse", "smoothing": "low"}}
    ops = [{"type": "addFeature", "feature": feature}]
    request = kernel.send(
        "surfacing.preview",
        {"baseRevision": head["revision"], "ops": ops},
        lane="surfacing.preview:auto-surface",
    )
    preview = kernel.wait(request, timeout=180).result
    # Progress events are throttled, so short stages may not appear.
    assert {stage.value for stage in ProgressStage} & _progress_stages(kernel)
    assert preview["status"]["state"] == "ok", preview["status"]
    assert preview["status"]["stats"]["patches"] == 1200
    assert len(preview["bodies"]) == 1 and preview["bodies"][0]["valid"]

    applied = kernel.call(
        "doc.apply", {"baseRevision": head["revision"], "ops": ops, "label": "autoSurface"}
    )
    assert applied.ok, applied.header.get("error")
    after = kernel.call("doc.get").result
    body = after["status"]["bodies"][0]
    assert body["valid"] and len(body["faceTags"]) == 1200


def _progress_stages(kernel: KernelProcess) -> set[str]:
    """Stages of the progress events received so far."""
    stages: set[str] = set()
    while True:
        try:
            event = kernel.next_event("progress", timeout=0.5)
        except queue.Empty:
            return stages
        stages.add(event["data"]["stage"])
