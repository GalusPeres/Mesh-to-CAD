"""Freeform nets: clean quad nets, fitting, the limit map, the feature and the net.* commands."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import BRepAdaptor_Surface, BRepCheck_Analyzer
from m2c_kernel.document.rebuild import rebuild
from m2c_kernel.export.api import check_body
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from m2c_kernel.surfacing.cage import compact
from m2c_kernel.surfacing.net import (
    NetError,
    fit_net,
    generate_net,
    limit_map,
    net_deviation,
    net_shape,
)
from m2c_kernel.surfacing.quadmesh import QuadNet, clean_quad_net, quad_net, remesh_in_process
from m2c_kernel.surfacing.subdivision import edge_topology, limit_matrix
from tests.kernel_process import KernelProcess
from tests.surfacing import shapes
from tests.surfacing.conftest import scan_document, with_feature
from tests.synthetic import write_binary_stl

pytestmark = pytest.mark.occt

type FloatArray = np.ndarray


def in_process(
    vertices: FloatArray, faces: np.ndarray, count: int, crease: float
) -> tuple[FloatArray, np.ndarray]:
    """Instant Meshes in the test process (the kernel runs it in a child process)."""
    return remesh_in_process(vertices.astype(np.float32), faces.astype(np.uint32), count, crease)


def sphere_net(target: int = 600) -> tuple[shapes.OrganicScan, QuadNet]:
    scan = shapes.sphere()
    normals = vertex_normals(scan.vertices, scan.faces)
    return scan, generate_net(scan.vertices, scan.faces, normals, target, remesh=in_process)


def quad_normals(vertices: FloatArray, quads: np.ndarray) -> FloatArray:
    p = vertices
    normals: FloatArray = np.cross(p[quads[:, 2]] - p[quads[:, 0]], p[quads[:, 3]] - p[quads[:, 1]])
    return normals


# Quad nets ----------------------------------------------------------------------------------


def test_quad_net_is_a_closed_manifold_facing_outwards() -> None:
    scan = shapes.sphere()
    normals = vertex_normals(scan.vertices, scan.faces)
    net = quad_net(scan.vertices, scan.faces, normals, 600, remesh=in_process)
    assert 400 <= len(net.quads) <= 900
    topology = edge_topology(net.quads, len(net.vertices))
    assert not np.any(topology.boundary)
    centres = net.vertices[net.quads].mean(axis=1)
    outward = np.einsum("ij,ij->i", quad_normals(net.vertices, net.quads), centres) > 0
    assert outward.mean() > 0.99


def test_inward_nets_are_flipped_and_stray_parts_dropped() -> None:
    scan, net = sphere_net()
    # Reverse every quad and add a separate stray quad far away.
    stray = np.array([[0, 0, 100], [1, 0, 100], [1, 1, 100], [0, 1, 100]], dtype=np.float64)
    vertices = np.concatenate([net.vertices, stray])
    quads = np.concatenate([net.quads[:, ::-1], [np.arange(4) + len(net.vertices)]])
    cleaned = clean_quad_net(
        vertices, quads, scan.vertices, vertex_normals(scan.vertices, scan.faces)
    )
    assert len(cleaned.quads) == len(net.quads)
    assert len(cleaned.vertices) == len(net.vertices)
    centres = cleaned.vertices[cleaned.quads].mean(axis=1)
    normals = quad_normals(cleaned.vertices, cleaned.quads)
    assert (np.einsum("ij,ij->i", normals, centres) > 0).mean() > 0.99


# Shape, deviation and fitting ---------------------------------------------------------------


def test_generated_net_gives_a_closed_bspline_solid_close_to_the_scan() -> None:
    from OCP.GeomAbs import GeomAbs_BSplineSurface

    scan, net = sphere_net()
    shape = net_shape(net.vertices, net.quads)
    assert shape.closed and shape.packed
    assert BRepCheck_Analyzer(shape.shape).IsValid()
    assert len(shape.faces) < len(net.quads) / 3
    assert {BRepAdaptor_Surface(face).GetType() for face in shape.faces} == {GeomAbs_BSplineSurface}
    deviation = net_deviation(shape, scan.vertices)
    assert deviation is not None and deviation.count == len(scan.vertices)
    assert deviation.rms < 2.0 * scan.sigma
    assert deviation.max < 8.0 * scan.sigma


def test_fit_moves_free_points_back_and_keeps_fixed_points() -> None:
    scan, net = sphere_net()
    centre_dirs = net.vertices / np.linalg.norm(net.vertices, axis=1, keepdims=True)
    moved = net.vertices + 1.0 * centre_dirs
    fixed = np.zeros(len(moved), dtype=bool)
    fixed[: len(moved) // 4] = True
    normals = vertex_normals(scan.vertices, scan.faces)
    fitted = fit_net(moved, net.quads, scan.vertices, normals, fixed=fixed, iterations=4)
    np.testing.assert_allclose(fitted[fixed], moved[fixed], atol=1e-4)
    free_before = np.abs(
        np.linalg.norm(moved[~fixed], axis=1) - np.linalg.norm(net.vertices[~fixed], axis=1)
    )
    free_after = np.abs(
        np.linalg.norm(fitted[~fixed], axis=1) - np.linalg.norm(net.vertices[~fixed], axis=1)
    )
    assert np.median(free_after) < 0.5 * np.median(free_before)


def test_open_net_does_not_grow_over_the_rest_of_the_scan() -> None:
    scan = shapes.sphere()
    centroids = scan.vertices[scan.faces].mean(axis=1)
    cap_vertices, cap_faces = compact(scan.vertices, scan.faces[centroids[:, 2] > 5.0])
    cap_normals = vertex_normals(cap_vertices, cap_faces)
    net = generate_net(cap_vertices, cap_faces, cap_normals, 300, remesh=in_process)
    topology = edge_topology(net.quads, len(net.vertices))
    assert np.any(topology.boundary)
    # Fit the open cap against the whole sphere: the border must stay near z = 5.
    normals = vertex_normals(scan.vertices, scan.faces)
    fitted = fit_net(net.vertices, net.quads, scan.vertices, normals, iterations=6)
    border = np.unique(topology.edges[topology.boundary])
    limits = limit_matrix(net.quads, len(net.vertices)) @ fitted
    assert limits[border, 2].min() > 2.0


# Limit map ------------------------------------------------------------------------------------


def test_limit_map_starts_with_the_limit_points_of_the_control_points() -> None:
    _, net = sphere_net()
    result = limit_map(net.quads, len(net.vertices), level=2)
    n = len(net.vertices)
    dense = result.matrix @ net.vertices
    limits = limit_matrix(net.quads, n) @ net.vertices
    # The first fine vertices are the limit positions of the control points.
    np.testing.assert_allclose(dense[:n], limits, atol=1e-9)
    assert len(result.triangles) == len(net.quads) * 16 * 2
    # Every net edge is drawn with 2^level segments, each once.
    assert len(result.segments) == len(result.edges) * 4
    assert np.array_equal(np.bincount(result.segment_edges), np.full(len(result.edges), 4))
    assert not np.any(result.border)
    # The outlines of the CAD faces: a closed sphere net packs into few faces.
    assert result.face_edges.shape == (len(result.edges),)
    assert 1 < result.face_count < len(net.quads) / 3


def test_limit_map_rejects_broken_nets() -> None:
    quads = np.array([[0, 1, 2, 3], [0, 1, 2, 3]], dtype=np.int64)
    with pytest.raises(NetError):
        limit_map(quads, 4)


# Feature --------------------------------------------------------------------------------------


def _net_params(
    session: Session, net: QuadNet, faces: np.ndarray | None = None
) -> dict[str, object]:
    params: dict[str, object] = {
        "vertices": session.blobs.put(net.vertices.astype(np.float64)),
        "quads": session.blobs.put(net.quads.astype(np.uint32)),
        "faces": None if faces is None else session.blobs.put(faces.astype(np.uint32)),
    }
    return params


def test_closed_net_feature_gives_a_body(session: Session, job: JobContext) -> None:
    scan, net = sphere_net()
    document = with_feature(
        scan_document(session, scan.vertices, scan.faces, scan.sigma),
        "f1",
        "freeformNet",
        _net_params(session, net),  # type: ignore[arg-type]
    )
    result = rebuild(document, session.environment(), job)
    status = result.statuses["f1"]
    assert status.state == "ok", status.error
    assert status.stats["quads"] == len(net.quads) and status.stats["closed"] == 1.0
    faces = status.stats["patches"]
    assert faces is not None and faces < len(net.quads) / 3
    rms = status.stats["deviationRms"]
    assert rms is not None and rms < 2.0 * scan.sigma
    body = result.outputs["f1"].bodies.changed["f1"]
    assert len(body.face_tags) == faces and body.face_tags[0].startswith("f1:patch:")
    check = check_body(body)
    assert not check.blocking and check.closed and check.solids == 1


def test_open_net_feature_is_a_construction_surface(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    centroids = scan.vertices[scan.faces].mean(axis=1)
    selected = np.flatnonzero(centroids[:, 2] > 5.0)
    cap_vertices, cap_faces = compact(scan.vertices, scan.faces[selected])
    net = generate_net(
        cap_vertices, cap_faces, vertex_normals(cap_vertices, cap_faces), 300, remesh=in_process
    )
    document = with_feature(
        scan_document(session, scan.vertices, scan.faces, scan.sigma),
        "f1",
        "freeformNet",
        _net_params(session, net, selected),  # type: ignore[arg-type]
    )
    result = rebuild(document, session.environment(), job)
    status = result.statuses["f1"]
    assert status.state == "warning"
    assert [issue.code for issue in status.issues] == ["surfacing.openNet"]
    output = result.outputs["f1"]
    assert output.construction is not None and output.construction.surface is not None
    assert not output.bodies.changed
    rms = status.stats["deviationRms"]
    assert rms is not None and rms < 3.0 * scan.sigma


def test_broken_net_feature_fails_with_a_code(session: Session, job: JobContext) -> None:
    scan = shapes.sphere()
    broken = QuadNet(np.zeros((4, 3)), np.array([[0, 1, 2, 3], [0, 1, 2, 3]], dtype=np.int64))
    document = with_feature(
        scan_document(session, scan.vertices, scan.faces, scan.sigma),
        "f1",
        "freeformNet",
        _net_params(session, broken),  # type: ignore[arg-type]
    )
    status = rebuild(document, session.environment(), job).statuses["f1"]
    assert status.state == "error"
    assert status.error is not None and status.error.code == "surfacing.netInvalid"


# Protocol ------------------------------------------------------------------------------------


def _buffer(index: int, array: np.ndarray) -> dict[str, object]:
    return {"$buf": index, "dtype": str(array.dtype), "shape": list(array.shape)}


def test_generate_limit_map_and_commit_through_the_protocol(
    kernel: KernelProcess, tmp_path: Path
) -> None:
    scan = shapes.blob()
    path = write_binary_stl(tmp_path / "blob.stl", scan.vertices, scan.faces)
    report = kernel.call("mesh.import", {"path": str(path)}, origin="main").result
    assert kernel.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"}).ok

    generated = kernel.call(
        "net.generate", {"targetQuads": 800}, lane="net.generate:freeform-net", timeout=180
    )
    assert generated.ok, generated.header.get("error")
    result = generated.result
    vertices = np.frombuffer(generated.buffers[result["vertices"]["$buf"]], np.float64).reshape(
        -1, 3
    )
    quads = np.frombuffer(generated.buffers[result["quads"]["$buf"]], np.uint32).reshape(-1, 4)
    assert 500 <= len(quads) <= 1200

    mapped = kernel.call(
        "net.limitMap",
        {"quads": _buffer(0, quads), "vertexCount": len(vertices)},
        buffers=[quads],
        lane="net.limitMap:freeform-net",
    )
    assert mapped.ok, mapped.header.get("error")
    assert mapped.result["level"] == 3
    assert mapped.result["fineCount"] > len(vertices)

    head = kernel.call("doc.get").result
    feature = {
        "type": "freeformNet",
        "params": {"vertices": _buffer(0, vertices), "quads": _buffer(1, quads)},
    }
    applied = kernel.call(
        "doc.apply",
        {
            "baseRevision": head["revision"],
            "ops": [{"type": "addFeature", "feature": feature}],
            "label": "freeformNet",
        },
        buffers=[vertices, quads],
        timeout=120,
    )
    assert applied.ok, applied.header.get("error")
    after = kernel.call("doc.get").result
    body = after["status"]["bodies"][0]
    assert body["valid"] and 0 < len(body["faceTags"]) < len(quads) / 3

    feature_id = after["document"]["features"][0]["id"]
    stored = kernel.call("net.featureNet", {"featureId": feature_id})
    assert stored.ok
    stored_quads = np.frombuffer(stored.buffers[stored.result["quads"]["$buf"]], np.uint32)
    assert np.array_equal(stored_quads.reshape(-1, 4), quads)
    assert stored.result["faces"] is None
