"""The mesh methods through a real kernel process: lanes, buffers, reduction in a child."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tests.kernel_process import KernelProcess
from tests.mesh.dirty import dirty_box_scan
from tests.synthetic import write_binary_stl


def _import(kernel: KernelProcess, path: Path) -> dict[str, object]:
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    commit = kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"})
    assert commit.ok
    snapshot = kernel.call("doc.get").result
    assert isinstance(snapshot, dict)
    return snapshot


def test_preparation_previews_and_commits_over_the_protocol(
    kernel: KernelProcess, tmp_path: Path
) -> None:
    scan = dirty_box_scan()
    snapshot = _import(kernel, write_binary_stl(tmp_path / "dirty.stl", *vars(scan.mesh).values()))
    face_count = snapshot["document"]["scan"]["faceCount"]  # type: ignore[index]

    preview = kernel.call(
        "mesh.fillHoles",
        {"maxPerimeter": 30.0, "dryRun": True},
        lane="mesh.fillHoles:mesh-fill-holes",
    )
    result = preview.result
    assert result["changed"] and result["revision"] is None
    affected = result["affectedFaces"]
    assert affected["dtype"] == "uint32"
    faces = np.frombuffer(preview.buffers[affected["$buf"]], dtype=np.uint32)
    assert len(faces) == affected["shape"][0] > 0
    assert faces.max() < face_count

    reduced = kernel.call("mesh.decimate", {"targetFaces": 20_000})
    assert reduced.result["counts"]["facesBefore"] == face_count
    after = kernel.call("doc.get").result
    assert after["document"]["scan"]["faceCount"] <= 20_000
    assert after["document"]["scan"]["operations"][-1]["op"] == "decimate"

    key = after["document"]["scan"]["key"]
    selection = np.arange(0, 500, dtype=np.uint32)
    deleted = kernel.call(
        "mesh.deleteFaces",
        {"faces": {"$buf": 0, "dtype": "uint32", "shape": [500]}, "scanKey": key},
        buffers=[selection],
    )
    assert deleted.result["counts"] == {"deletedFaces": 500}
    stale = kernel.call(
        "mesh.deleteFaces",
        {"faces": {"$buf": 0, "dtype": "uint32", "shape": [500]}, "scanKey": key},
        buffers=[selection],
    )
    assert stale.error_code == "mesh.staleSelection"
