"""The fit workflow through the framed protocol, as the renderer drives it.

Import a scan, preview a fit of a selection in the tool's lane, commit it with
`doc.apply` (triangles as a buffer inside the operation), read its triangles
back for editing, and build a plane through its axis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from tests.fitting.helpers import combine, noisy_patch
from tests.kernel_process import KernelProcess
from tests.synthetic import write_binary_stl

RADIUS = 8.0


def _buffer(index: int, array: np.ndarray) -> dict[str, Any]:
    return {"$buf": index, "dtype": "uint32", "shape": [len(array)]}


def _scan_faces(kernel: KernelProcess, scan_key: str) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (relative to the scan origin) and faces of the imported scan."""
    manifest = kernel.call("doc.get").result["scene"]["scan"]
    fetched = kernel.call("scene.fetch", {"keys": [manifest["key"]]})
    payload = fetched.result["payloads"][0]
    positions = np.frombuffer(fetched.buffers[payload["positions"]["$buf"]], np.float32)
    indices = np.frombuffer(fetched.buffers[payload["indices"]["$buf"]], np.uint32)
    assert manifest["scanKey"] == scan_key
    return positions.reshape(-1, 3).astype(np.float64) + manifest["origin"], indices.reshape(-1, 3)


def test_fit_preview_commit_and_reference(kernel: KernelProcess, tmp_path: Path) -> None:
    hole = noisy_patch("cylinder", np.radians(150), 20.0, 1, pose=False, radius=RADIUS)
    plane = noisy_patch("plane", 30.0, 30.0, 2, pose=False)
    vertices, faces = combine(
        (hole.vertices, hole.faces), (plane.vertices + np.array([40.0, 0.0, 15.0]), plane.faces)
    )
    path = write_binary_stl(tmp_path / "part.stl", vertices, faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok
    assert kernel.next_event("documentChanged")["data"]["label"] == "import"
    scan_key = kernel.call("doc.get").result["document"]["scan"]["key"]

    points, triangles = _scan_faces(kernel, scan_key)
    centroids = points[triangles].mean(axis=1)
    on_hole = np.abs(np.hypot(centroids[:, 0], centroids[:, 1]) - RADIUS) < 0.3
    selection = np.nonzero(on_hole & (centroids[:, 0] < 20.0))[0].astype(np.uint32)

    preview = kernel.call(
        "fit.preview",
        {"faces": _buffer(0, selection), "scanKey": scan_key, "kind": "auto"},
        buffers=[selection],
        lane="fit.preview:fit-primitive",
    ).result
    assert preview["primitive"]["type"] == "cylinder"
    assert preview["primitive"]["radius"] == RADIUS
    assert [snap["id"] for snap in preview["snaps"]] == ["direction", "radius"]
    assert preview["stats"]["passed"] is True
    assert preview["faceStates"]["shape"] == [len(selection)]
    assert {item["style"] for item in preview["items"]} == {"construction", "constructionEdges"}

    revision = kernel.call("doc.get").result["revision"]
    params = {"faces": _buffer(0, selection), "kind": "cylinder"}
    ops = [{"type": "addFeature", "feature": {"type": "fit", "params": params}}]
    applied = kernel.call(
        "doc.apply",
        {"baseRevision": revision, "ops": ops, "label": "fit"},
        buffers=[selection],
    )
    changed = kernel.next_event("documentChanged")
    fit_id = changed["data"]["document"]["features"][0]["id"]
    status = changed["data"]["status"]["features"][fit_id]
    assert applied.result["revision"] == changed["data"]["revision"]
    assert status["state"] == "ok"
    assert status["stats"]["radius"] == RADIUS

    stored = kernel.call("fit.featureFaces", {"featureId": fit_id})
    np.testing.assert_array_equal(np.frombuffer(stored.buffers[0], np.uint32), np.sort(selection))

    definition = {"type": "planeThroughAxis", "axis": fit_id, "angleDeg": 90.0}
    ops = [
        {
            "type": "addFeature",
            "feature": {"type": "reference", "params": {"definition": definition}},
        }
    ]
    kernel.call("doc.apply", {"baseRevision": applied.result["revision"], "ops": ops, "label": "r"})
    changed = kernel.next_event("documentChanged")
    reference_id = changed["data"]["document"]["features"][1]["id"]
    reference = changed["data"]["status"]["features"][reference_id]
    assert reference["state"] == "ok"
    # About Z at 90 degrees: the YZ plane through the hole axis.
    assert abs(abs(reference["stats"]["directionX"]) - 1.0) < 1e-9
