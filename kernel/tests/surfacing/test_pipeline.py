"""`auto_surface` on noisy organic shapes: closed, valid, all B-spline, close to the scan."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import (
    BRepAdaptor_Surface,
    BRepCheck_Analyzer,
    TopAbs_FACE,
    indexed_map,
)
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.surfacing.api import SurfaceModel, SurfacingOptions, auto_surface
from m2c_kernel.surfacing.cage import Decimator, validate_cage
from m2c_kernel.surfacing.collapse import collapse_to
from tests.surfacing import shapes

pytestmark = pytest.mark.occt

ARMADILLO = Path(__file__).resolve().parents[3] / ".work" / "samples" / "stanford-armadillo.ply"
MAX_RELATIVE_RMS = 0.005
"""RMS deviation limit as a share of the bounding box diagonal."""


def _assert_bspline_solid(model: SurfaceModel) -> None:
    from OCP.GeomAbs import GeomAbs_BSplineSurface

    assert model.closed
    assert model.shape.ShapeType().name == "TopAbs_SOLID"
    assert BRepCheck_Analyzer(model.shape).IsValid()
    assert indexed_map(model.shape, TopAbs_FACE).Extent() == model.patch_count
    assert model.patch_count == len(model.cage_quads)
    types = {BRepAdaptor_Surface(face).GetType() for face in model.faces}
    assert types == {GeomAbs_BSplineSurface}


@pytest.mark.parametrize("shape", [shapes.sphere, shapes.torus, shapes.blob])
def test_organic_shapes_become_closed_bspline_solids(
    shape: object, job: JobContext, decimator: Decimator
) -> None:
    scan = shape()  # type: ignore[operator]
    model = auto_surface(
        scan.vertices,
        scan.faces,
        SurfacingOptions.from_levels("coarse", "low"),
        job,
        decimate=decimator,
    )
    _assert_bspline_solid(model)
    assert model.ignored_parts == 0
    # The surface follows the scan within its noise and a small fitting share.
    assert model.deviation.rms < 2.0 * scan.sigma
    assert model.deviation.rms < MAX_RELATIVE_RMS * scan.diagonal
    assert model.deviation.max < 8.0 * scan.sigma


def test_decimation_in_child_process(job: JobContext) -> None:
    scan = shapes.sphere()
    model = auto_surface(
        scan.vertices, scan.faces, SurfacingOptions.from_levels("coarse", "low"), job
    )
    _assert_bspline_solid(model)
    assert model.deviation.rms < 2.0 * scan.sigma


def test_more_detail_gives_more_patches(job: JobContext, decimator: Decimator) -> None:
    scan = shapes.blob()
    counts = [
        auto_surface(
            scan.vertices,
            scan.faces,
            SurfacingOptions.from_levels(detail, "medium"),
            job,
            decimate=decimator,
        ).patch_count
        for detail in ("coarse", "medium")
    ]
    assert counts[0] < counts[1]


def test_open_scan_gives_open_shell(job: JobContext, decimator: Decimator) -> None:
    scan = shapes.sphere()
    centroids = scan.vertices[scan.faces].mean(axis=1)
    faces = scan.faces[centroids[:, 2] > -5.0]
    model = auto_surface(
        scan.vertices, faces, SurfacingOptions.from_levels("coarse", "low"), job, decimate=decimator
    )
    assert not model.closed
    assert model.shape.ShapeType().name == "TopAbs_SHELL"
    assert BRepCheck_Analyzer(model.shape).IsValid()
    assert model.deviation.rms < 2.0 * scan.sigma


def test_too_few_faces(job: JobContext, decimator: Decimator) -> None:
    scan = shapes.sphere()
    with pytest.raises(KernelError) as raised:
        auto_surface(
            scan.vertices,
            scan.faces[:100],
            SurfacingOptions.from_levels("coarse", "low"),
            job,
            decimate=decimator,
        )
    assert raised.value.code == "surfacing.tooFewFaces"


def test_collapse_keeps_thin_parts_manifold(decimator: Decimator) -> None:
    # A thin torus folds into non-manifold edges when quadric decimation alone
    # reduces it to a cage; the manifold collapse does not.
    scan = shapes.torus(major=40.0, minor=1.5, sigma=0.0)
    vertices, faces = decimator(scan.vertices, scan.faces, 6000)
    validate_cage(vertices, faces)
    cage_vertices, cage_faces = collapse_to(vertices, faces, 200)
    topology = validate_cage(cage_vertices, cage_faces)
    assert not np.any(topology.boundary)
    assert len(cage_faces) <= 260
    # Euler characteristic of a torus.
    assert len(cage_vertices) - len(topology.edges) + len(cage_faces) == 0


def test_collapse_keeps_open_boundaries(decimator: Decimator) -> None:
    scan = shapes.sphere(sigma=0.0)
    centroids = scan.vertices[scan.faces].mean(axis=1)
    faces = scan.faces[centroids[:, 2] > 0.0]
    cage_vertices, cage_faces = collapse_to(scan.vertices, faces, 300)
    topology = validate_cage(cage_vertices, cage_faces)
    border = np.unique(topology.edges[topology.boundary])
    assert len(border) >= 8
    # The border stays on the equator.
    assert np.all(np.abs(cage_vertices[border, 2]) < 2.0)


@pytest.mark.slow
@pytest.mark.skipif(not ARMADILLO.exists(), reason="Armadillo sample not present")
@pytest.mark.parametrize("detail", ["coarse", "medium", "fine"])
def test_armadillo(detail: str, job: JobContext, decimator: Decimator) -> None:
    import trimesh

    mesh = trimesh.load_mesh(ARMADILLO, process=False)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)))
    start = time.perf_counter()
    model = auto_surface(
        vertices,
        faces,
        SurfacingOptions.from_levels(detail, "low"),  # type: ignore[arg-type]
        job,
        decimate=decimator,
    )
    elapsed = time.perf_counter() - start
    _assert_bspline_solid(model)
    relative = model.deviation.rms / diagonal
    print(
        f"\nArmadillo {detail}: {model.patch_count} patches, {elapsed:.1f} s, "
        f"RMS {model.deviation.rms:.3f} mm ({100 * relative:.3f} % of {diagonal:.1f} mm), "
        f"max {model.deviation.max:.2f} mm"
    )
    assert relative < MAX_RELATIVE_RMS
