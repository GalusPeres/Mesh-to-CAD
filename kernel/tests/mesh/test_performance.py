"""Import time of a full-size scan (ARCHITECTURE.md 1.5: 2 M faces including repair < 10 s)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.commands.mesh import (
    CommitImportParams,
    ImportParams,
    mesh_commit_import,
    mesh_import,
)
from m2c_kernel.session.jobs import JobContext, seeded_rng
from m2c_kernel.session.session import Session
from tests.synthetic import add_scanner_noise, write_binary_stl
from tests.timing import budget


def _noisy_torus(around: int, tube: int) -> tuple[np.ndarray, np.ndarray]:
    """A closed torus (R 60, r 20 mm) with 2 * around * tube faces and scanner noise."""
    u = np.linspace(0, 2 * np.pi, around, endpoint=False)
    v = np.linspace(0, 2 * np.pi, tube, endpoint=False)
    uu, vv = (grid.ravel() for grid in np.meshgrid(u, v, indexing="ij"))
    normals = np.stack([np.cos(vv) * np.cos(uu), np.cos(vv) * np.sin(uu), np.sin(vv)], axis=1)
    ring = 60.0 + 20.0 * np.cos(vv)
    points = np.stack([ring * np.cos(uu), ring * np.sin(uu), 20.0 * np.sin(vv)], axis=1)
    points = add_scanner_noise(points, normals, 0.03, seeded_rng("torus"), spike_fraction=0.001)
    i, j = np.meshgrid(np.arange(around), np.arange(tube), indexing="ij")
    a = i * tube + j
    b = ((i + 1) % around) * tube + j
    c = ((i + 1) % around) * tube + (j + 1) % tube
    d = i * tube + (j + 1) % tube
    faces = np.concatenate(
        [np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)]
    )
    return points, faces.astype(np.int64)


@pytest.mark.slow
def test_a_two_million_face_stl_imports_with_repair_in_under_ten_seconds(
    session: Session, job: JobContext, tmp_path: Path
) -> None:
    vertices, faces = _noisy_torus(1250, 800)
    path = write_binary_stl(tmp_path / "large.stl", vertices, faces)
    start = time.perf_counter()
    report = mesh_import(job, ImportParams(path=str(path)))
    result = mesh_commit_import(job, CommitImportParams(pending_id=report.pending_id, unit="mm"))
    elapsed = time.perf_counter() - start
    scan = session.document.scan
    assert scan is not None and scan.face_count == 2_000_000
    assert result.counts["mergedVertices"] == 6_000_000 - 1_000_000
    assert report.noise["mm"] is not None and 0.02 < report.noise["mm"] < 0.045
    assert elapsed < budget(10.0), f"import took {elapsed:.1f} s"
