"""Freeform patch and loft through the protocol, as the tool panels call them."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.freeform.shapes import tube_scan, tube_volume
from tests.kernel_process import KernelProcess
from tests.synthetic import write_binary_stl

pytestmark = pytest.mark.occt


def test_patch_preview_and_loft_commit(kernel: KernelProcess, tmp_path: Path) -> None:
    vertices, faces = tube_scan(sigma=0.02)
    path = write_binary_stl(tmp_path / "tube.stl", vertices, faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok
    head = kernel.call("doc.get").result
    assert head["scene"]["scan"]["faceCount"] == len(faces)

    # A patch on the side of the tube: triangles facing +X between z = 10 and z = 40.
    centroids = vertices[faces].mean(axis=1)
    side = np.nonzero(
        (centroids[:, 2] > 10)
        & (centroids[:, 2] < 40)
        & (centroids[:, 1] > -6)
        & (centroids[:, 1] < 6)
        & (centroids[:, 0] > 5)
    )[0].astype(np.uint32)
    request = kernel.send(
        "freeform.preview",
        {"faces": {"$buf": 0, "dtype": "uint32", "shape": [len(side)]}, "spans": [8, 6]},
        lane="freeform.preview:freeform-patch",
        buffers=[side],
    )
    preview = kernel.wait(request).result
    assert preview["spans"] == [8, 6]
    assert preview["passed"] and preview["rms"] < 0.03
    assert {item["style"] for item in preview["items"]} == {"patch"}

    loft = {"type": "loft", "params": {"path": "Z", "start": 3.0, "end": 57.0, "sectionCount": 12}}
    ops = [{"type": "addFeature", "feature": loft}]
    shown = kernel.call(
        "doc.preview", {"baseRevision": head["revision"], "ops": ops}, lane="doc.preview:loft"
    ).result
    assert shown["status"]["state"] == "ok", shown["status"]
    assert shown["bodies"][0]["volume"] == pytest.approx(tube_volume(3.0, 57.0), rel=2e-3)
    applied = kernel.call(
        "doc.apply", {"baseRevision": head["revision"], "ops": ops, "label": "loft"}
    )
    assert applied.ok, applied.header.get("error")
    after = kernel.call("doc.get").result
    tags = after["status"]["bodies"][0]["faceTags"]
    assert sorted(tags) == [
        f"{shown['featureId']}:{tag}" for tag in ("cap:end", "cap:start", "loft:0")
    ]
