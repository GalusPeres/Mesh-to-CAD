"""Smart select: region growing from a seed face on the noisy test block."""

from __future__ import annotations

import time

import numpy as np
import pytest

from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.segmentation.api import GrowMode, grow_region, prepare
from m2c_kernel.session.jobs import seeded_rng
from tests.segmentation.conftest import NoisyPart, noisy_block

pytestmark = pytest.mark.occt


def _grow(
    block: NoisyPart, brep_face: int, mode: GrowMode = "primitive"
) -> tuple[float, str | None]:
    seed = block.interior_face(brep_face)
    grown = grow_region(block.mesh, seed, mode, seeded_rng(f"test:{brep_face}"))
    return block.iou(grown.faces, brep_face), grown.kind


def test_primitive_growth_finds_the_top_plane(small_block: NoisyPart) -> None:
    # z = 20, cut by the boss, the hole and the dimple
    iou, kind = _grow(small_block, small_block.plane_face((0.0, 0.0, 1.0), 20.0))
    assert kind == "plane"
    assert iou >= 0.95


def test_primitive_growth_finds_the_hole(small_block: NoisyPart) -> None:
    (hole,) = small_block.cylinder_faces(8.0)
    iou, kind = _grow(small_block, hole)
    assert kind == "cylinder"
    assert iou >= 0.95


def test_primitive_growth_finds_a_tangent_r6_fillet(small_block: NoisyPart) -> None:
    fillets = small_block.cylinder_faces(6.0)
    assert len(fillets) == 4
    for fillet in fillets:
        iou, kind = _grow(small_block, fillet)
        assert kind == "cylinder"
        assert iou >= 0.85


def test_primitive_growth_reports_the_sphere(small_block: NoisyPart) -> None:
    iou, kind = _grow(small_block, small_block.face_of("sphere"))
    assert kind == "sphere"
    assert iou >= 0.8


def test_normal_mode_selects_the_faces_facing_like_the_seed(small_block: NoisyPart) -> None:
    # the R3 fillet at the base of the boss is tangent to the top plane, so the
    # normal mode reaches 10 degrees into it
    top = small_block.plane_face((0.0, 0.0, 1.0), 20.0)
    iou, kind = _grow(small_block, top, "normal")
    assert kind is None
    assert iou >= 0.85


def test_smooth_mode_follows_tangent_surfaces_across_fillets(small_block: NoisyPart) -> None:
    # the side walls and the R6 fillets form one tangent-continuous band; the
    # 90 degree edges to the top and bottom planes are creases
    side = small_block.plane_face((1.0, 0.0, 0.0), 100.0)
    seed = small_block.interior_face(side)
    grown = grow_region(small_block.mesh, seed, "smooth", seeded_rng("test:smooth"))
    reached = np.bincount(small_block.part.labels[grown.faces], minlength=16)
    truth = np.bincount(small_block.part.labels, minlength=16)
    for fillet in small_block.cylinder_faces(6.0):
        assert reached[fillet] > 0.5 * truth[fillet]
    top = small_block.plane_face((0.0, 0.0, 1.0), 20.0)
    assert reached[top] < 0.01 * truth[top]
    assert grown.kind is None


def test_a_given_kind_is_used_as_is(small_block: NoisyPart) -> None:
    (hole,) = small_block.cylinder_faces(8.0)
    seed = small_block.interior_face(hole)
    grown = grow_region(small_block.mesh, seed, "primitive", seeded_rng("kind"), kind="cylinder")
    assert grown.kind == "cylinder"
    assert grown.rms is not None and grown.rms < 0.06


def test_synthetic_faces_never_seed_or_join_a_region(small_block: NoisyPart) -> None:
    block = small_block
    synthetic = np.zeros(len(block.mesh.faces), dtype=bool)
    top = block.plane_face((0.0, 0.0, 1.0), 20.0)
    seed = block.interior_face(top)
    members = np.nonzero(block.truth(top))[0]
    synthetic[members[::7]] = True
    synthetic[seed] = False
    mesh = EvalMesh("mesh:synthetic", block.mesh.vertices, block.mesh.faces, synthetic)
    grown = grow_region(mesh, seed, "primitive", seeded_rng("synthetic"))
    assert len(grown.faces) > 1000
    assert not synthetic[grown.faces].any()
    empty = grow_region(mesh, int(members[0]), "primitive", seeded_rng("synthetic seed"))
    assert len(empty.faces) == 0 and empty.kind is None


@pytest.mark.slow
def test_growth_on_a_million_faces_takes_less_than_a_second() -> None:
    block = noisy_block(1.0)
    assert len(block.mesh.faces) > 900_000
    prepare(block.mesh, lambda: None)
    targets = {
        "plane": block.plane_face((0.0, 0.0, 1.0), 20.0),
        "cylinder": block.cylinder_faces(8.0)[0],
        "sphere": block.face_of("sphere"),
    }
    for kind, brep_face in targets.items():
        seed = block.interior_face(brep_face)
        start = time.perf_counter()
        grown = grow_region(block.mesh, seed, "primitive", seeded_rng(f"timing:{kind}"))
        assert time.perf_counter() - start < 1.0
        assert grown.kind == kind
