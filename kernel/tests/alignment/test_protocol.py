"""The alignment through the protocol: import, preview, commit, as the renderer does it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.kernel_process import KernelProcess
from tests.synthetic import box_scan, random_rotation, write_binary_stl

pytestmark = pytest.mark.occt


def _import(kernel: KernelProcess, path: Path) -> None:
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    commit = kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"})
    assert commit.ok, commit.header.get("error")


def test_preview_and_commit_over_the_protocol(kernel: KernelProcess, tmp_path: Path) -> None:
    vertices, faces = box_scan((80.0, 50.0, 12.0), max_edge=2.0, sigma=0.02, seed=3)
    rotation = random_rotation(np.random.default_rng(8))
    posed = vertices @ rotation.T + np.array([120.0, -40.0, 15.0])
    _import(kernel, write_binary_stl(tmp_path / "box.stl", posed, faces))

    auto = kernel.call("alignment.preview", {"method": "auto"}, lane="alignment.preview:align-auto")
    assert auto.result["largestPlane"]["plane"] == "XY"
    assert auto.result["largestPlane"]["tiltDeg"] < 0.01
    assert auto.result["params"] is None

    # The bottom of the box (design z = 0) as a selection: faces whose centroids lie there.
    centroids = posed[faces].mean(axis=1)
    design = (centroids - np.array([120.0, -40.0, 15.0])) @ rotation
    bottom = np.nonzero(np.abs(design[:, 2]) < 0.05)[0].astype(np.uint32)
    side = np.nonzero(np.abs(design[:, 1]) < 0.05)[0].astype(np.uint32)
    buffer = {"dtype": "uint32"}
    params = {
        "method": "faces",
        "primary": {"type": "selection", "faces": {"$buf": 0, **buffer, "shape": [len(bottom)]}},
        "secondary": {"type": "selection", "faces": {"$buf": 1, **buffer, "shape": [len(side)]}},
        "adjust": {"flipX": False, "flipZ": False, "rotateZ90": 1},
    }
    request = kernel.send("alignment.preview", params, buffers=[bottom, side])
    faces_preview = kernel.wait(request).result
    assert [fit["role"] for fit in faces_preview["inputs"]] == ["primary", "secondary"]
    stored = faces_preview["params"]
    assert stored["primary"]["type"] == "faces" and stored["primary"]["faces"].startswith("blob:")

    revision = kernel.call("doc.get").result["revision"]
    apply = kernel.call(
        "doc.apply",
        {
            "baseRevision": revision,
            "ops": [
                {
                    "type": "setAlignment",
                    "method": "faces",
                    "params": stored,
                    "adjust": {"rotateZ90": 1},
                }
            ],
            "label": "alignment",
        },
    )
    assert apply.ok, apply.header.get("error")
    changed = [event for event in apply.events if event.get("event") == "documentChanged"]
    snapshot = changed[-1]["data"] if changed else kernel.call("doc.get").result
    assert snapshot["document"]["alignment"]["method"] == "faces"
    np.testing.assert_allclose(snapshot["scene"]["scan"]["transform"], faces_preview["matrix"])
