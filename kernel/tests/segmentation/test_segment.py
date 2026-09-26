"""Automatic segmentation of the noisy test block: accuracy, time, progress, cancellation."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np
import pytest

from m2c_kernel.codes.regions import ProgressStage
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.geometry import IDENTITY
from m2c_kernel.protocol.errors import Cancelled
from m2c_kernel.segmentation.api import LevelOfDetailCache, Segmentation, segment
from m2c_kernel.session.jobs import JobContext, seeded_rng
from tests.segmentation.conftest import NoisyPart, noisy_block

pytestmark = pytest.mark.occt


@dataclass(frozen=True)
class Run:
    result: Segmentation
    seconds: float
    progress: list[tuple[float | None, str]]


def _segment(block: NoisyPart, job: JobContext, faces: np.ndarray | None = None) -> Segmentation:
    lod = LevelOfDetailCache().get(block.mesh, f"scan:{block.mesh.key}", IDENTITY, job)
    return segment(block.mesh, lod, 50.0, 2.0, job, seeded_rng("test:segment"), faces)


def _run(block: NoisyPart) -> Run:
    progress: list[tuple[float | None, str]] = []
    job = JobContext(1, None, lambda fraction, stage: progress.append((fraction, stage)))
    start = time.perf_counter()
    result = _segment(block, job)
    return Run(result, time.perf_counter() - start, progress)


def _ious(block: NoisyPart, labels: np.ndarray) -> list[float]:
    """IoU by area of the best matching region for every true B-Rep face."""
    area = block.mesh.face_areas
    labels = labels.astype(np.int64)
    ious = []
    for brep_face in range(len(block.part.surfaces)):
        truth = block.truth(brep_face)
        best = int(np.argmax(np.bincount(labels[truth], weights=area[truth])))
        region = labels == best
        ious.append(float(area[region & truth].sum() / area[region | truth].sum()))
    return ious


@pytest.fixture(scope="module")
def small_run(small_block: NoisyPart) -> Run:
    return _run(small_block)


def test_the_block_splits_into_its_sixteen_surfaces(small_block: NoisyPart, small_run: Run) -> None:
    count = len(small_run.result.kinds)
    ious = _ious(small_block, small_run.result.labels)
    assert 14 <= count <= 18
    assert np.mean(ious) >= 0.92
    assert small_run.seconds < 30.0


def test_regions_report_the_type_of_their_surface(small_block: NoisyPart, small_run: Run) -> None:
    labels = small_run.result.labels.astype(np.int64)
    expected = {
        small_block.plane_face((0.0, 0.0, 1.0), 20.0): "plane",
        small_block.plane_face((0.0, 0.0, -1.0), 0.0): "plane",
        small_block.cylinder_faces(8.0)[0]: "cylinder",
        small_block.face_of("sphere"): "sphere",
        small_block.face_of("torus"): "torus",
    }
    for fillet in small_block.cylinder_faces(6.0):
        expected[fillet] = "cylinder"
    for brep_face, kind in expected.items():
        best = int(np.argmax(np.bincount(labels[small_block.truth(brep_face)])))
        assert best > 0
        assert small_run.result.kinds[best - 1] == kind
        assert 0.02 < small_run.result.rms[best - 1] < 0.06


def test_progress_is_reported_per_accepted_region(small_run: Run) -> None:
    growing = [
        fraction
        for fraction, stage in small_run.progress
        if stage == ProgressStage.GROWING and fraction is not None
    ]
    assert len(growing) >= 3
    assert growing == sorted(growing)
    stages = {stage for _, stage in small_run.progress}
    assert {ProgressStage.REDUCING, ProgressStage.TRANSFERRING} <= stages


def test_segmenting_a_subset_leaves_the_other_faces_unassigned(small_block: NoisyPart) -> None:
    # the top plane and everything above it (boss, fillet, chamfer, dimple)
    upper = np.nonzero(small_block.mesh.face_centroids[:, 2] > 19.95)[0]
    result = _segment(small_block, JobContext.detached(), upper)
    outside = np.ones(len(small_block.mesh.faces), dtype=bool)
    outside[upper] = False
    assert not result.labels[outside].any()
    top = small_block.plane_face((0.0, 0.0, 1.0), 20.0)
    assert _ious(small_block, result.labels)[top] >= 0.9


@pytest.mark.parametrize("delay", [0.3, 1.5, 3.0])
def test_cancelling_returns_within_a_second(small_block: NoisyPart, delay: float) -> None:
    # a fresh mesh object, so the reduction and the analysis run again
    block = NoisyPart(
        small_block.part,
        EvalMesh(f"mesh:cancel{delay}", small_block.mesh.vertices, small_block.mesh.faces, None),
    )
    cancel = threading.Event()
    job = JobContext(1, None, None, cancel)
    outcome: dict[str, float] = {}

    def work() -> None:
        try:
            _segment(block, job)
        except Cancelled:
            outcome["cancelled"] = time.perf_counter()

    worker = threading.Thread(target=work)
    worker.start()
    time.sleep(delay)
    cancelled_at = time.perf_counter()
    cancel.set()
    worker.join(timeout=10)
    assert "cancelled" in outcome, "segmentation finished before it could be cancelled"
    assert outcome["cancelled"] - cancelled_at < 1.0


@pytest.mark.slow
def test_the_full_size_block_is_segmented_accurately_within_twenty_seconds() -> None:
    block = noisy_block(1.0)
    assert len(block.mesh.faces) > 900_000
    run = _run(block)
    ious = _ious(block, run.result.labels)
    assert 14 <= len(run.result.kinds) <= 18
    assert np.mean(ious) >= 0.94
    assert run.seconds < 20.0
