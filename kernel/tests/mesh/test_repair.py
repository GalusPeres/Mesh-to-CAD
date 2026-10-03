"""Repair, small parts and hole filling on a scan with known defects."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.mesh.load import RawMesh
from m2c_kernel.mesh.repair import (
    MeshChange,
    boundary_loops,
    delete_faces,
    fill_holes,
    fix_winding,
    orient_outward,
    remove_small_parts,
    repair,
    signed_volume,
)
from m2c_kernel.mesh.topology import edge_topology
from tests.mesh.dirty import (
    DEBRIS_PARTS,
    DEGENERATES,
    DUPLICATES,
    HOLE_CENTRES,
    HOLE_RADIUS,
    DirtyScan,
    dirty_box_scan,
)
from tests.synthetic import primitive_patch, sphere_scan


@pytest.fixture(scope="module")
def dirty() -> DirtyScan:
    return dirty_box_scan()


@pytest.fixture(scope="module")
def cleaned(dirty: DirtyScan) -> MeshChange:
    repaired = repair(dirty.mesh)
    return repaired.then(remove_small_parts(repaired.mesh))


def test_repair_counts_exactly_what_was_injected(dirty: DirtyScan, cleaned: MeshChange) -> None:
    counts = cleaned.counts
    assert counts["degenerateFaces"] == DEGENERATES
    assert counts["duplicateFaces"] == DUPLICATES
    assert counts["flippedFaces"] == len(dirty.flipped)
    assert counts["nonOrientableFaces"] == 0
    assert counts["invertedParts"] == 0
    assert counts["removedParts"] == DEBRIS_PARTS
    assert counts["removedFaces"] == len(dirty.debris_faces)


def test_repaired_scan_is_consistent_and_outward(cleaned: MeshChange) -> None:
    topology = edge_topology(cleaned.mesh.faces)
    assert topology.inconsistent_edge_count() == 0
    assert topology.non_manifold_edge_count == 0
    assert signed_volume(cleaned.mesh) == pytest.approx(100 * 70 * 20, rel=0.01)


def test_all_debris_is_removed_and_the_part_is_kept(dirty: DirtyScan, cleaned: MeshChange) -> None:
    sources = set(cleaned.new_to_old.tolist())
    removed_debris = len(set(dirty.debris_faces.tolist()) - sources)
    assert removed_debris / len(dirty.debris_faces) >= 0.95
    assert set(dirty.clean_faces.tolist()) <= sources


def test_face_map_is_exact(dirty: DirtyScan, cleaned: MeshChange) -> None:
    new_mesh, old_mesh = cleaned.mesh, dirty.mesh
    assert (cleaned.new_to_old >= 0).all()
    new_corners = np.sort(new_mesh.vertices[new_mesh.faces].reshape(-1, 9), axis=1)
    old_corners = np.sort(old_mesh.vertices[old_mesh.faces[cleaned.new_to_old]].reshape(-1, 9), 1)
    np.testing.assert_array_equal(new_corners, old_corners)
    flipped_now = np.isin(cleaned.new_to_old, dirty.flipped)
    same_order = (new_mesh.faces == _renumbered(old_mesh, new_mesh, cleaned)).all(axis=1)
    assert not same_order[flipped_now].any()
    assert same_order[~flipped_now].all()


def _renumbered(old: RawMesh, new: RawMesh, change: MeshChange) -> np.ndarray:
    """Old faces in the vertex numbering of the new mesh."""
    lookup = {tuple(point): index for index, point in enumerate(new.vertices.tolist())}
    old_faces = old.faces[change.new_to_old]
    return np.array([[lookup[tuple(old.vertices[v].tolist())] for v in face] for face in old_faces])


def test_holes_are_filled_and_only_new_faces_are_synthetic(
    dirty: DirtyScan, cleaned: MeshChange
) -> None:
    before = boundary_loops(cleaned.mesh)
    assert len(before.loops) == dirty.holes and before.skipped == 0
    filled = fill_holes(cleaned.mesh, max_perimeter=30.0)
    assert filled.counts["filledHoles"] == dirty.holes
    assert filled.counts["openHoles"] == 0
    assert (filled.synthetic == (filled.new_to_old < 0)).all()
    assert filled.synthetic.sum() == filled.counts["addedFaces"]
    assert (filled.new_to_old[~filled.synthetic] == np.arange(len(cleaned.mesh.faces))).all()
    topology = edge_topology(filled.mesh.faces)
    assert (topology.valence == 2).all()
    assert topology.inconsistent_edge_count() == 0


def test_holes_above_the_perimeter_limit_stay_open(cleaned: MeshChange) -> None:
    filled = fill_holes(cleaned.mesh, max_perimeter=5.0)
    assert filled.counts["filledHoles"] == 0
    assert filled.counts["openHoles"] == 3
    assert len(filled.mesh.faces) == len(cleaned.mesh.faces)


def test_hole_filling_follows_a_curved_surface() -> None:
    patch = primitive_patch("cylinder", np.pi, 40.0, resolution=120, radius=10.0)
    mesh = RawMesh(patch.vertices, patch.faces)
    centroids = mesh.vertices[mesh.faces].mean(axis=1)
    hole = np.linalg.norm(centroids - np.array([10.0, 0.0, 0.0]), axis=1) < 2.0
    holed = delete_faces(mesh, np.flatnonzero(hole))
    filled = fill_holes(holed.mesh, max_perimeter=20.0)
    assert filled.counts["filledHoles"] == 1
    centre = filled.mesh.vertices[-1]
    radial = np.hypot(centre[0], centre[1])
    loop_centroid = holed.mesh.vertices[boundary_loops(holed.mesh).loops[0]].mean(axis=0)
    assert abs(radial - 10.0) < 0.01
    assert abs(np.hypot(loop_centroid[0], loop_centroid[1]) - 10.0) > 0.05


def test_winding_fix_flips_the_minority() -> None:
    vertices, faces = sphere_scan(subdivisions=3)
    faces = faces.copy()
    faces[:10] = faces[:10, ::-1]
    change = fix_winding(RawMesh(vertices, faces))
    assert change.counts["flippedFaces"] == 10
    assert edge_topology(change.mesh.faces).inconsistent_edge_count() == 0
    assert signed_volume(change.mesh) > 0


def test_each_inside_out_part_is_turned_separately() -> None:
    vertices, faces = sphere_scan(subdivisions=2)
    second = faces[:, ::-1] + len(vertices)
    shifted = vertices + np.array([100.0, 0.0, 0.0])
    mesh = RawMesh(np.vstack([vertices, shifted]), np.vstack([faces, second]))
    change = orient_outward(mesh)
    assert change.counts["invertedParts"] == 1
    assert (change.mesh.faces[: len(faces)] == faces).all()
    assert (change.mesh.faces[len(faces) :] == faces + len(vertices)).all()


def test_a_single_sided_patch_is_left_as_it_is() -> None:
    patch = primitive_patch("plane", 40.0, 40.0, resolution=30)
    flipped = RawMesh(patch.vertices, patch.faces[:, ::-1].copy())
    assert orient_outward(flipped).counts["invertedParts"] == 0


def test_small_parts_keep_separate_bodies_of_similar_size() -> None:
    vertices, faces = sphere_scan(subdivisions=3)
    mesh = RawMesh(
        np.vstack([vertices, vertices + 50.0]), np.vstack([faces, faces + len(vertices)])
    )
    change = remove_small_parts(mesh)
    assert change.counts["removedParts"] == 0
    assert len(change.mesh.faces) == len(mesh.faces)


def test_deleting_faces_drops_unused_vertices() -> None:
    vertices, faces = sphere_scan(subdivisions=2)
    change = delete_faces(RawMesh(vertices, faces), np.arange(0, len(faces), 2))
    assert change.counts["deletedFaces"] == len(faces) // 2
    assert np.array_equal(change.new_to_old, np.arange(1, len(faces), 2))
    used = np.zeros(len(change.mesh.vertices), dtype=bool)
    used[change.mesh.faces.ravel()] = True
    assert used.all()


def test_repair_leaves_a_clean_mesh_unchanged() -> None:
    vertices, faces = sphere_scan(subdivisions=3)
    change = repair(RawMesh(vertices, faces))
    assert np.array_equal(change.mesh.faces, faces)
    assert np.array_equal(change.mesh.vertices, vertices)
    assert change.counts["mergedVertices"] == 0


def test_affected_faces_name_what_each_step_touches(dirty: DirtyScan) -> None:
    repaired = repair(dirty.mesh)
    injected = np.arange(len(dirty.clean_faces) + len(dirty.debris_faces), len(dirty.mesh.faces))
    assert np.array_equal(repaired.affected, np.union1d(dirty.flipped, injected))
    small = remove_small_parts(repaired.mesh)
    assert np.array_equal(repaired.new_to_old[small.affected], dirty.debris_faces)
    cleaned = repaired.then(small)
    filled = fill_holes(cleaned.mesh, max_perimeter=30.0)
    centroids = cleaned.mesh.vertices[cleaned.mesh.faces[filled.affected]].mean(axis=1)
    distance = np.min(
        [np.hypot(centroids[:, 0] - x, centroids[:, 1] - y) for x, y in HOLE_CENTRES], axis=0
    )
    assert len(filled.affected) > 3 * 8
    assert (distance < HOLE_RADIUS + 1.5).all()
    assert np.allclose(centroids[:, 2], 20.0, atol=0.3)
