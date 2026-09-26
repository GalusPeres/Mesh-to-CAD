"""Measured end-to-end scenarios through a real kernel process (docs/RESULTS.md).

Usage: node scripts/py.mjs scripts/verify_scenarios.py [armadillo|plate ...] [--out file.json]

1. Armadillo scan -> automatic surfaces (medium) -> cylinder hole (primitive body + combine
   cut) -> STEP export -> read back with OCCT: valid solid, freeform faces are B-splines.
2. Noisy test plate (flange with three holes) -> plane and cylinder fits -> section sketch
   through the middle -> extrusion to the fitted top plane -> STEP -> dimension errors.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kernel"))

from tests.kernel_process import KernelProcess
from tests.synthetic import write_binary_stl

ARMADILLO = ROOT / ".work" / "samples" / "stanford-armadillo.ply"


def buf(index: int, array: np.ndarray) -> dict[str, Any]:
    return {"$buf": index, "dtype": "uint32", "shape": [len(array)]}


def start(session: Path) -> KernelProcess:
    kernel = KernelProcess(session, debug_commands=False)
    kernel.next_event("ready", timeout=60)
    assert kernel.call("system.info").ok
    return kernel


def import_scan(
    kernel: KernelProcess, path: Path
) -> tuple[str, np.ndarray, np.ndarray]:
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main", timeout=300)
    assert report.ok, report.header
    committed = kernel.call(
        "mesh.commitImport",
        {"pendingId": report.result["pendingId"], "unit": "mm"},
        timeout=300,
    )
    assert committed.ok, committed.header
    head = kernel.call("doc.get").result
    manifest = head["scene"]["scan"]
    fetched = kernel.call("scene.fetch", {"keys": [manifest["key"]]}, timeout=120)
    payload = fetched.result["payloads"][0]
    positions = np.frombuffer(fetched.buffers[payload["positions"]["$buf"]], np.float32)
    indices = np.frombuffer(fetched.buffers[payload["indices"]["$buf"]], np.uint32)
    points = positions.reshape(-1, 3).astype(np.float64) + manifest["origin"]
    return head["document"]["scan"]["key"], points, indices.reshape(-1, 3)


def apply(
    kernel: KernelProcess,
    ops: list[dict[str, Any]],
    label: str,
    buffers: list[np.ndarray] | None = None,
) -> dict[str, Any]:
    revision = kernel.call("doc.get").result["revision"]
    applied = kernel.call(
        "doc.apply",
        {"baseRevision": revision, "ops": ops, "label": label},
        buffers=buffers or [],
        timeout=900,
    )
    assert applied.ok, applied.header.get("error")
    return kernel.call("doc.get").result


def new_feature_id(before: dict[str, Any], after: dict[str, Any]) -> str:
    old = {feature["id"] for feature in before["document"]["features"]}
    ids = [f["id"] for f in after["document"]["features"] if f["id"] not in old]
    assert len(ids) == 1, ids
    return str(ids[0])


def feature_status(head: dict[str, Any], feature_id: str) -> dict[str, Any]:
    status = head["status"]["features"][feature_id]
    assert status["state"] in ("ok", "warning"), status
    return dict(status)


def body_info(head: dict[str, Any], body_id: str) -> dict[str, Any]:
    """The body with this id, or else the body the feature `body_id` last changed."""
    bodies = head["status"]["bodies"]
    for body in bodies:
        if body["id"] == body_id:
            return dict(body)
    for body in reversed(bodies):
        if body["owner"] == body_id:
            return dict(body)
    raise LookupError((body_id, [(b["id"], b["owner"]) for b in bodies]))


def export_and_read_back(
    kernel: KernelProcess, body: str, path: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    exported = kernel.call(
        "export.step",
        {"path": str(path), "bodies": [body], "names": ["scenario"], "schema": "AP214"},
        origin="main",
        timeout=600,
    )
    assert exported.ok, exported.header.get("error")
    seconds = time.perf_counter() - started
    info = read_step(path)
    info["exportSeconds"] = round(seconds, 2)
    info["fileMB"] = round(path.stat().st_size / 1e6, 2)
    return info


def read_step(path: Path) -> dict[str, Any]:
    """Independent read-back with plain OCCT (not the kernel's own export check)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    reader.TransferRoots()
    shape = reader.OneShape()
    solids = 0
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids += 1
        explorer.Next()
    kinds: dict[str, int] = {}
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        surface = BRepAdaptor_Surface(TopoDS.Face(explorer.Current()))
        name = str(surface.GetType().name).removeprefix("GeomAbs_")
        kinds[name] = kinds.get(name, 0) + 1
        explorer.Next()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return {
        "valid": bool(BRepCheck_Analyzer(shape).IsValid()),
        "solids": solids,
        "faces": sum(kinds.values()),
        "faceTypes": kinds,
        "volume": round(props.Mass(), 3),
    }


def deviation(kernel: KernelProcess, bodies: list[str]) -> dict[str, Any]:
    result = kernel.call(
        "inspection.deviation", {"bodies": bodies, "maxDistance": 20.0}, timeout=600
    )
    assert result.ok, result.header.get("error")
    return dict(result.result["stats"])


# ------------------------------------------------------------------------------------------


def armadillo(work: Path) -> dict[str, Any]:
    kernel = start(work / "session-armadillo")
    try:
        t0 = time.perf_counter()
        _, points, faces = import_scan(kernel, ARMADILLO)
        import_seconds = time.perf_counter() - t0
        diagonal = float(np.linalg.norm(points.max(0) - points.min(0)))

        before = kernel.call("doc.get").result
        t0 = time.perf_counter()
        feature = {
            "type": "autoSurface",
            "params": {"detail": "medium", "smoothing": "low"},
        }
        head = apply(
            kernel, [{"type": "addFeature", "feature": feature}], "autoSurface"
        )
        surface_seconds = time.perf_counter() - t0
        surface_id = new_feature_id(before, head)
        stats = feature_status(head, surface_id).get("stats", {})
        surfaced = body_info(head, surface_id)
        body_id = surfaced["id"]
        surfaced_deviation = deviation(kernel, [body_id])

        # A 6 mm hole through the torso, along the thinnest direction of the scan.
        centre = np.median(points, axis=0)
        centred = points - points.mean(axis=0)
        _, _, axes = np.linalg.svd(
            centred[:: max(1, len(centred) // 50_000)], full_matrices=False
        )
        direction = axes[-1]
        radius = 6.0
        centroids = points[faces].mean(axis=1)
        rel = centroids - centre
        radial = np.linalg.norm(rel - np.outer(rel @ direction, direction), axis=1)
        near = np.nonzero(np.abs(radial - radius) < 3.0)[0].astype(np.uint32)
        if len(near) < 50:
            near = np.argsort(np.abs(radial - radius))[:500].astype(np.uint32)

        before = head
        fixed = {
            "direction": direction.tolist(),
            "point": centre.tolist(),
            "radius": radius,
        }
        fit = {"faces": buf(0, near), "kind": "cylinder", "fixed": fixed, "snap": False}
        head = apply(
            kernel,
            [{"type": "addFeature", "feature": {"type": "fit", "params": fit}}],
            "fit",
            [near],
        )
        fit_id = new_feature_id(before, head)

        t0 = time.perf_counter()
        before = head
        extent = {"type": "manual", "start": -400.0, "length": 800.0}
        primitive = {
            "type": "primitiveBody",
            "params": {"fit": fit_id, "extent": extent},
        }
        head = apply(
            kernel, [{"type": "addFeature", "feature": primitive}], "primitiveBody"
        )
        tool_id = new_feature_id(before, head)
        before = head
        combine = {
            "type": "combine",
            "params": {
                "targetBody": body_id,
                "tools": [body_info(head, tool_id)["id"]],
                "operation": "cut",
            },
        }
        head = apply(kernel, [{"type": "addFeature", "feature": combine}], "combine")
        combine_id = new_feature_id(before, head)
        feature_status(head, combine_id)
        cut_seconds = time.perf_counter() - t0
        cut = body_info(head, body_id)

        step = export_and_read_back(kernel, body_id, work / "armadillo-with-hole.step")
        freeform = {k: v for k, v in step["faceTypes"].items() if k != "Cylinder"}
        return {
            "scanTriangles": len(faces),
            "diagonalMm": round(diagonal, 1),
            "importSeconds": round(import_seconds, 1),
            "autoSurfaceSeconds": round(surface_seconds, 1),
            "patches": stats.get("patches"),
            "kernelStats": stats,
            "surfaceBody": {k: surfaced.get(k) for k in ("valid", "solids", "volume")},
            "deviation": surfaced_deviation,
            "holeRadiusMm": radius,
            "cutSeconds": round(cut_seconds, 1),
            "cutBody": {k: cut.get(k) for k in ("valid", "solids", "volume")},
            "volumeRemovedMm3": round(surfaced["volume"] - cut["volume"], 1),
            "step": step,
            "freeformFacesAllBSpline": set(freeform) <= {"BSplineSurface"},
        }
    finally:
        kernel.stop()


def plate(work: Path) -> dict[str, Any]:
    from m2c_kernel.mesh.normals import vertex_normals
    from tests.synthetic.noise import add_scanner_noise
    from tests.synthetic.parts import plate_part

    sigma = 0.03
    part = plate_part()
    rng = np.random.default_rng(7)
    noisy = add_scanner_noise(
        part.vertices, vertex_normals(part.vertices, part.faces), sigma, rng
    )
    path = write_binary_stl(work / "flange.stl", noisy, part.faces)

    kernel = start(work / "session-plate")
    try:
        t_all = time.perf_counter()
        _, _, faces = import_scan(kernel, path)
        # Ground truth per triangle from the tessellation (import keeps the triangle order).
        assert len(faces) == len(part.faces)
        centroids = part.vertices[part.faces].mean(axis=1)
        normals = np.cross(
            part.vertices[part.faces[:, 1]] - part.vertices[part.faces[:, 0]],
            part.vertices[part.faces[:, 2]] - part.vertices[part.faces[:, 0]],
        )
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        top = np.nonzero(
            (np.abs(centroids[:, 2] - 10) < 0.01) & (normals[:, 2] > 0.99)
        )[0]
        bottom = np.nonzero((np.abs(centroids[:, 2]) < 0.01) & (normals[:, 2] < -0.99))[
            0
        ]
        radial = np.hypot(centroids[:, 0], centroids[:, 1] - 30)
        hole = np.nonzero((np.abs(radial - 10) < 0.05) & (np.abs(normals[:, 2]) < 0.1))[
            0
        ]

        ids: dict[str, str] = {}
        results: dict[str, Any] = {}
        for name, selection, kind in (
            ("top", top, "plane"),
            ("bottom", bottom, "plane"),
            ("hole", hole, "cylinder"),
        ):
            before = kernel.call("doc.get").result
            chosen = selection.astype(np.uint32)
            params = {"faces": buf(0, chosen), "kind": kind}
            head = apply(
                kernel,
                [{"type": "addFeature", "feature": {"type": "fit", "params": params}}],
                f"fit {name}",
                [chosen],
            )
            ids[name] = new_feature_id(before, head)
            results[name] = feature_status(head, ids[name]).get("stats", {})

        # Section sketch on the bottom plane fit, cut through the middle of the plate.
        section: dict[str, Any] = {
            "type": "planar",
            "plane": {"type": "feature", "feature": ids["bottom"]},
            "sectionOffset": -5.0,
        }
        fitted = kernel.call(
            "sketch.autoFit", {"sketch": {"section": section}}, timeout=120
        )
        if not fitted.ok or not fitted.result["sketch"]["entities"]:
            section["sectionOffset"] = 5.0
            fitted = kernel.call(
                "sketch.autoFit", {"sketch": {"section": section}}, timeout=120
            )
        assert fitted.ok, fitted.header.get("error")
        sketch = fitted.result["sketch"]
        before = kernel.call("doc.get").result
        head = apply(
            kernel,
            [{"type": "addFeature", "feature": {"type": "sketch", "params": sketch}}],
            "sketch",
        )
        sketch_id = new_feature_id(before, head)
        feature_status(head, sketch_id)

        before = head
        extrude: dict[str, Any] = {}
        for direction in ("normal", "reversed"):
            extrude = {
                "sketch": sketch_id,
                "direction": direction,
                "extent": {"type": "toPlane", "feature": ids["top"]},
            }
            op = [
                {
                    "type": "addFeature",
                    "feature": {"type": "extrude", "params": extrude},
                }
            ]
            preview = kernel.call(
                "doc.preview",
                {"baseRevision": head["revision"], "ops": op},
                lane="doc.preview:x",
            )
            if preview.ok and preview.result["status"]["state"] == "ok":
                break
        head = apply(
            kernel,
            [{"type": "addFeature", "feature": {"type": "extrude", "params": extrude}}],
            "x",
        )
        extrude_id = new_feature_id(before, head)
        feature_status(head, extrude_id)
        body = body_info(head, extrude_id)
        if not body.get("valid") or body.get("volume", 0) < 1:
            raise AssertionError(body)
        total_seconds = time.perf_counter() - t_all
        dev = deviation(kernel, [body["id"]])
        step = export_and_read_back(kernel, body["id"], work / "flange.step")

        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from tests.synthetic.parts import build_test_plate

        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(build_test_plate(), props)
        true_volume = props.Mass()

        entities = sketch["entities"]
        radii = sorted(round(e["radius"], 4) for e in entities if "radius" in e)
        return {
            "sigmaMm": sigma,
            "scanTriangles": len(faces),
            "fits": results,
            "sketchEntities": {
                kind: sum(1 for e in entities if e["type"] == kind)
                for kind in sorted({e["type"] for e in entities})
            },
            "sketchRadii": radii,
            "trueRadii": [6, 6, 8, 8, 8, 10],
            "radiusErrorsMm": [
                round(a - b, 4)
                for a, b in zip(radii, [6, 6, 8, 8, 8, 10], strict=False)
            ],
            "body": {k: body.get(k) for k in ("valid", "solids", "volume")},
            "trueVolume": round(true_volume, 3),
            "volumeErrorPct": round(
                100 * (body["volume"] - true_volume) / true_volume, 4
            ),
            "deviation": dev,
            "workflowSeconds": round(total_seconds, 1),
            "step": step,
        }
    finally:
        kernel.stop()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = None
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        args = [
            a
            for a in args
            if a != str(out) and a != sys.argv[sys.argv.index("--out") + 1]
        ]
    wanted = args or ["plate", "armadillo"]
    work = Path(tempfile.mkdtemp(prefix="m2c-scenarios-"))
    results: dict[str, Any] = {}
    for name in wanted:
        started = time.perf_counter()
        results[name] = {"armadillo": armadillo, "plate": plate}[name](work)
        results[name]["totalSeconds"] = round(time.perf_counter() - started, 1)
        print(json.dumps({name: results[name]}, indent=1, default=str), flush=True)
    if out:
        out.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
