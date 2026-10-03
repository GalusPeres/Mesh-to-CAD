"""Reduction in a child process, its cancellation, and display smoothing."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from m2c_kernel.mesh.decimate import decimate
from m2c_kernel.mesh.load import RawMesh
from m2c_kernel.mesh.smoothing import taubin
from m2c_kernel.mesh.topology import edge_topology
from m2c_kernel.protocol.errors import Cancelled
from m2c_kernel.session.jobs import JobContext
from tests.synthetic import sphere_scan


@pytest.fixture(scope="module")
def dense_sphere() -> RawMesh:
    vertices, faces = sphere_scan(radius=20.0, subdivisions=7, sigma=0.02)
    return RawMesh(vertices, faces)


def test_reduction_reaches_the_target_without_unused_vertices(dense_sphere: RawMesh) -> None:
    change = decimate(dense_sphere, 100_000)
    reduced = change.mesh
    assert 90_000 <= len(reduced.faces) <= 100_000
    assert change.counts == {
        "facesBefore": len(dense_sphere.faces),
        "facesAfter": len(reduced.faces),
    }
    used = np.zeros(len(reduced.vertices), dtype=bool)
    used[reduced.faces.ravel()] = True
    assert used.all()
    radius = np.linalg.norm(reduced.vertices, axis=1)
    assert np.abs(radius - 20.0).max() < 0.2
    assert len(change.new_to_old) == len(reduced.faces)
    assert (change.new_to_old >= 0).all() and not change.synthetic.any()


def test_reduction_is_cancelled_within_a_second(dense_sphere: RawMesh) -> None:
    cancelled = threading.Event()
    job = JobContext(0, None, cancel_event=cancelled)
    cancel_at: list[float] = []

    def cancel() -> None:
        cancel_at.append(time.monotonic())
        cancelled.set()

    timer = threading.Timer(0.25, cancel)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            decimate(dense_sphere, 1_000, job.check_cancelled)
    finally:
        timer.cancel()
    assert time.monotonic() - cancel_at[0] < 1.0


def test_a_target_above_the_face_count_changes_nothing() -> None:
    vertices, faces = sphere_scan(subdivisions=2)
    change = decimate(RawMesh(vertices, faces), 10_000)
    assert change.mesh.faces is faces or np.array_equal(change.mesh.faces, faces)
    assert change.counts["facesAfter"] == len(faces)


def test_taubin_smoothing_reduces_noise_and_keeps_the_size() -> None:
    clean, faces = sphere_scan(radius=20.0, subdivisions=5)
    noisy, _ = sphere_scan(radius=20.0, subdivisions=5, sigma=0.05)
    smoothed = taubin(noisy, faces, 10)
    before = np.abs(np.linalg.norm(noisy, axis=1) - 20.0)
    after = np.abs(np.linalg.norm(smoothed, axis=1) - 20.0)
    assert np.sqrt((after**2).mean()) < 0.5 * np.sqrt((before**2).mean())
    assert np.linalg.norm(smoothed, axis=1).mean() == pytest.approx(20.0, abs=0.01)
    assert edge_topology(faces).inconsistent_edge_count() == 0
    np.testing.assert_array_equal(taubin(clean, faces, 0), clean)
