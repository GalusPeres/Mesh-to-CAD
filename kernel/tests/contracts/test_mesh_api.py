"""Contracts of the shared mesh modules (topology, normals, remapping, loading)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.mesh.load import RawMesh, read_mesh, weld_vertices
from m2c_kernel.mesh.normals import face_normals, jet_fit, vertex_normals
from m2c_kernel.mesh.remap import remap_face_set, remap_labels
from m2c_kernel.mesh.topology import FaceGraph, edge_topology
from m2c_kernel.protocol.errors import KernelError
from tests.synthetic import add_scanner_noise, primitive_patch, sphere_scan, write_binary_stl


def test_a_closed_mesh_has_only_manifold_consistent_edges() -> None:
    _, faces = sphere_scan(subdivisions=3)
    topology = edge_topology(faces)
    assert (topology.valence == 2).all()
    assert topology.inconsistent_edge_count() == 0
    assert len(topology.boundary_half_edges) == 0


def test_an_open_patch_has_a_boundary() -> None:
    patch = primitive_patch("plane", 10, 10, resolution=11)
    topology = edge_topology(patch.faces)
    assert len(topology.boundary_half_edges) == 4 * 10
    assert topology.non_manifold_edge_count == 0


def test_flipped_faces_are_reported_as_inconsistent() -> None:
    _, faces = sphere_scan(subdivisions=2)
    faces = faces.copy()
    faces[0] = faces[0, ::-1]
    assert edge_topology(faces).inconsistent_edge_count() == 3


def test_face_graph_grows_across_the_whole_connected_surface() -> None:
    _, faces = sphere_scan(subdivisions=3)
    graph = FaceGraph(edge_topology(faces))
    assert graph.grow(0).all()
    assert graph.grow(0, max_rings=1).sum() == 4


def test_face_graph_respects_the_allowed_mask() -> None:
    patch = primitive_patch("plane", 10, 10, resolution=11)
    graph = FaceGraph(edge_topology(patch.faces))
    centroids = patch.vertices[patch.faces].mean(axis=1)
    left = centroids[:, 0] < 0
    region = graph.grow(int(np.argmax(left)), allowed=left)
    assert region.sum() == left.sum()
    labels = graph.components(left)
    assert (labels[~left] == -1).all()


def test_normals_point_outward_on_a_sphere() -> None:
    vertices, faces = sphere_scan(radius=20.0, subdivisions=3)
    normals = vertex_normals(vertices, faces)
    radial = vertices / np.linalg.norm(vertices, axis=1, keepdims=True)
    assert np.einsum("ij,ij->i", normals, radial).min() > 0.99
    unit_normals, areas = face_normals(vertices, faces)
    assert np.allclose(np.linalg.norm(unit_normals, axis=1), 1.0)
    assert areas.sum() == pytest.approx(4 * np.pi * 20.0**2, rel=0.01)


def test_jet_fit_estimates_noise_and_curvature() -> None:
    rng = np.random.default_rng(3)
    patch = primitive_patch("cylinder", np.pi, 30.0, resolution=160, radius=10.0)
    noisy = add_scanner_noise(patch.vertices, patch.normals, 0.02, rng)
    jet = jet_fit(noisy, vertex_normals(noisy, patch.faces))
    assert 0.012 < jet.noise < 0.03
    interior = np.abs(patch.vertices[:, 2]) < 10
    assert np.median(jet.k1[interior]) == pytest.approx(0.1, abs=0.03)
    angles = np.degrees(
        np.arccos(np.clip(np.einsum("ij,ij->i", jet.normals, patch.normals), -1, 1))
    )
    assert np.median(angles[interior]) < 2.0


def test_exact_face_maps_carry_face_sets_and_labels() -> None:
    new_to_old = np.array([0, 2, 3, -1, -1], dtype=np.int64)
    assert remap_face_set(np.array([2, 3]), new_to_old, old_face_count=4).tolist() == [1, 2]
    labels = np.array([5, 6, 7, 8], dtype=np.uint16)
    assert remap_labels(labels, new_to_old).tolist() == [5, 7, 8, 0, 0]


def test_reading_and_welding_an_stl(tmp_path: Path) -> None:
    vertices, faces = sphere_scan(subdivisions=2)
    raw = read_mesh(write_binary_stl(tmp_path / "part.stl", vertices, faces))
    assert len(raw.faces) == len(faces)
    welded, merged = weld_vertices(raw)
    assert len(welded.vertices) == len(vertices)
    assert merged == 3 * len(faces) - len(vertices)
    assert edge_topology(welded.faces).inconsistent_edge_count() == 0


def test_reading_rejects_unsupported_files(tmp_path: Path) -> None:
    path = tmp_path / "part.step"
    path.write_text("ISO-10303-21;")
    with pytest.raises(KernelError) as caught:
        read_mesh(path)
    assert caught.value.code == "mesh.unsupportedFormat"
    with pytest.raises(KernelError) as missing:
        read_mesh(tmp_path / "missing.stl")
    assert missing.value.code == "mesh.fileNotFound"


def test_raw_mesh_is_a_plain_container() -> None:
    mesh = RawMesh(np.zeros((3, 3)), np.array([[0, 1, 2]]))
    assert mesh.faces.shape == (1, 3)
