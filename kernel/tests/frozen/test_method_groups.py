"""One real call per method group against the frozen kernel.

Each probe does actual work on a noisy scanned box, so the libraries a group loads
lazily (scipy submodules, networkx through trimesh, OCP, the decimation child
process) are exercised in the frozen build. A group that the development kernel
registers but no probe covers fails `test_every_method_group_is_probed`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from m2c_kernel.protocol.registry import load_commands
from tests.frozen.conftest import requires_frozen_kernel
from tests.kernel_process import KernelProcess, Response
from tests.synthetic import box_scan, write_binary_stl

pytestmark = [pytest.mark.frozen, requires_frozen_kernel]

BOX = (100.0, 70.0, 20.0)


@dataclass
class Scanned:
    """A frozen kernel with the committed box scan and its displayed triangles."""

    kernel: KernelProcess
    scan_key: str
    positions: npt.NDArray[np.float32]
    indices: npt.NDArray[np.uint32]
    work: Path

    def faces_facing(self, direction: tuple[float, float, float]) -> npt.NDArray[np.uint32]:
        """Faces whose normal points along `direction` (one side of the box)."""
        corners = self.positions[self.indices]
        normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        return np.nonzero(normals @ np.asarray(direction) > 0.99)[0].astype(np.uint32)


def buffer_ref(index: int, array: np.ndarray) -> dict[str, Any]:
    return {"$buf": index, "dtype": str(array.dtype), "shape": list(array.shape)}


def array(response: Response, ref: dict[str, Any]) -> np.ndarray:
    data = np.frombuffer(response.buffers[ref["$buf"]], dtype=ref["dtype"])
    return data.reshape(ref["shape"])


def ok(response: Response) -> Any:
    assert response.ok, response.header.get("error")
    return response.result


@pytest.fixture
def scanned(frozen: KernelProcess, tmp_path: Path) -> Iterator[Scanned]:
    vertices, faces = box_scan(BOX, max_edge=2.0, sigma=0.03, seed=7)
    stl = write_binary_stl(tmp_path / "box.stl", vertices, faces)
    report = ok(frozen.call("mesh.import", {"path": str(stl)}, origin="main"))
    assert report["faceCount"] == len(faces)
    ok(frozen.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}))
    snapshot = ok(frozen.call("doc.get"))
    scene = snapshot["scene"]["scan"]
    fetched = frozen.call("scene.fetch", {"keys": [scene["key"]]})
    payload = ok(fetched)["payloads"][0]
    yield Scanned(
        kernel=frozen,
        scan_key=snapshot["document"]["scan"]["key"],
        positions=array(fetched, payload["positions"]).astype(np.float32),
        indices=array(fetched, payload["indices"]).astype(np.uint32),
        work=tmp_path,
    )


def probe_system(scanned: Scanned) -> None:
    info = ok(scanned.kernel.call("system.info"))
    assert info["occtVersion"].startswith("8.")
    assert ok(scanned.kernel.call("system.ping"))["time"] > 0


def probe_scene_and_doc(scanned: Scanned) -> None:
    kernel = scanned.kernel
    snapshot = ok(kernel.call("doc.get"))
    assert snapshot["document"]["scan"]["faceCount"] == len(scanned.indices)
    assert scanned.positions.shape[1] == 3
    revision = snapshot["revision"]
    ok(kernel.call("doc.checkout", {"revision": 0}))
    assert ok(kernel.call("doc.get"))["document"]["scan"] is None
    ok(kernel.call("doc.checkout", {"revision": revision}))


def probe_mesh(scanned: Scanned) -> None:
    kernel = scanned.kernel
    report = ok(kernel.call("mesh.inspect"))
    assert report["watertight"] is True
    assert ok(kernel.call("mesh.repair", {"dryRun": True}))["revision"] is None
    assert ok(kernel.call("mesh.setSmoothing", {"iterations": 2}))["revision"] > 0


def probe_project(scanned: Scanned) -> None:
    kernel = scanned.kernel
    path = scanned.work / "box.m2c"
    ok(kernel.call("project.save", {"path": str(path)}, origin="main"))
    ok(kernel.call("project.new"))
    loaded = ok(kernel.call("project.load", {"path": str(path)}, origin="main"))
    assert loaded["fileName"] == "box.m2c"
    assert ok(kernel.call("doc.get"))["document"]["scan"]["key"] == scanned.scan_key


def probe_fit(scanned: Scanned) -> None:
    top = scanned.faces_facing((0.0, 0.0, 1.0))
    params = {"faces": buffer_ref(0, top), "scanKey": scanned.scan_key, "kind": "auto"}
    result = ok(scanned.kernel.call("fit.preview", params, buffers=[top]))
    assert result["primitive"]["type"] == "plane"
    assert result["stats"]["rms"] < 0.1


def probe_sketch(scanned: Scanned) -> None:
    section = {"type": "planar", "plane": {"type": "standard", "plane": "XY"}, "offset": 10.0}
    result = ok(scanned.kernel.call("sketch.section", {"section": section}))
    assert result["polylines"], "the section through the box is empty"


def probe_alignment(scanned: Scanned) -> None:
    result = ok(scanned.kernel.call("alignment.preview", {"method": "auto"}))
    assert result["planeCount"] >= 2


def probe_inspection(scanned: Scanned) -> None:
    params = {"a": {"type": "origin", "item": "XY"}, "b": {"type": "origin", "item": "YZ"}}
    result = ok(scanned.kernel.call("inspection.measure", params))
    assert abs(result["angleDeg"]["value"] - 90.0) < 1e-6


def probe_export(scanned: Scanned) -> None:
    # The scanned box has no body yet; the command runs and reports exactly that.
    response = scanned.kernel.call("export.preflight", {"bodies": []})
    assert response.error_code == "export.noBody"


def probe_regions(scanned: Scanned) -> None:
    params = {"scanKey": scanned.scan_key, "sensitivity": 50, "dryRun": True}
    result = ok(scanned.kernel.call("regions.segment", params, timeout=120))
    kinds = [region["kind"] for region in result["regions"]]
    # A box has six planar sides.
    assert kinds.count("plane") >= 6, kinds


def probe_freeform(scanned: Scanned) -> None:
    top = scanned.faces_facing((0.0, 0.0, 1.0))
    params = {"faces": buffer_ref(0, top)}
    result = ok(scanned.kernel.call("freeform.preview", params, buffers=[top], timeout=120))
    assert result["faceCount"] == len(top)
    assert result["rms"] < 0.1


PROBES: dict[str, Callable[[Scanned], None]] = {
    "system": probe_system,
    "doc": probe_scene_and_doc,
    "scene": probe_scene_and_doc,
    "mesh": probe_mesh,
    "project": probe_project,
    "fit": probe_fit,
    "sketch": probe_sketch,
    "alignment": probe_alignment,
    "inspection": probe_inspection,
    "export": probe_export,
    "regions": probe_regions,
    "freeform": probe_freeform,
}

REGISTERED_GROUPS = sorted(
    {spec.group for spec in load_commands().values() if spec.caller != "test"}
)


def test_every_method_group_is_probed() -> None:
    assert set(REGISTERED_GROUPS) <= set(PROBES), "add a probe for the new method group"


@pytest.mark.parametrize("group", REGISTERED_GROUPS)
def test_method_group_works_frozen(group: str, scanned: Scanned) -> None:
    PROBES[group](scanned)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the kernel's protocol reader keeps a synchronous read pending on stdin, which "
        "blocks the start of every multiprocessing child (dev and frozen); fix requested "
        "in .work/interface-requests/T9.md (protect stdin in m2c_kernel/main.py)"
    ),
)
def test_decimation_runs_in_a_frozen_child_process(scanned: Scanned) -> None:
    """Reduction starts the frozen executable again (`--multiprocessing-fork`)."""
    before = len(scanned.indices)
    response = scanned.kernel.call("mesh.decimate", {"targetFaces": 4000}, timeout=60)
    result = ok(response)
    assert 3000 <= result["faceCount"] <= 4000 < before
