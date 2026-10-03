"""Height-field patches against a synthetic surface with known shape."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepCheck_Analyzer,
    GeomAPI_ProjectPointOnSurf,
    TopoDS,
    gp_Pnt,
    gp_Vec,
)
from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.heightfield import MAX_NORMAL_SPREAD_DEG, fit_patch
from m2c_kernel.freeform.occ import bspline_surface, patch_face
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.errors import KernelError
from tests.freeform.shapes import grid_faces, height_field_scan
from tests.synthetic import add_scanner_noise

pytestmark = pytest.mark.occt

SIGMA = 0.02


@pytest.fixture(scope="module")
def scan() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    field = height_field_scan(sigma=SIGMA)
    return field.vertices, field.faces, vertex_normals(field.vertices, field.faces)


def test_sixteen_by_twelve_spans_reach_the_noise_level(
    scan: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> None:
    vertices, _, normals = scan
    fit = fit_patch(vertices, normals, (16, 12), smoothing=1e-4, margin=2.0)
    assert fit.surface.spans == (16, 12)
    assert fit.rms <= 1.2 * SIGMA
    assert fit.max_abs < 8 * SIGMA
    face = patch_face(fit.surface)
    assert BRepCheck_Analyzer(face).IsValid()


def test_the_occt_surface_is_the_fitted_height_field(
    scan: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> None:
    vertices, _, normals = scan
    fit = fit_patch(vertices, normals, (16, 12), smoothing=1e-4, margin=2.0)
    surface = bspline_surface(fit.surface)
    sample = np.random.default_rng(0).choice(len(vertices), 300, replace=False)
    projected = []
    for index in sample:
        projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*vertices[index]), surface)
        projected.append(projector.LowerDistance())
    exact = np.abs(fit.deviations[sample])
    np.testing.assert_allclose(np.asarray(projected), exact, atol=2e-4)

    u0, u1, v0, v1 = fit.surface.domain
    u, v = np.array([u0, 0.5 * (u0 + u1), u1]), np.array([v0, 0.25 * v0 + 0.75 * v1, v1])
    expected = fit.surface.points(u, v)
    for point, pu, pv in zip(expected, u, v, strict=True):
        value = surface.Value(float(pu), float(pv))
        assert np.allclose([value.X(), value.Y(), value.Z()], point, atol=1e-9)


def test_the_face_normal_points_to_the_scanned_side(
    scan: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> None:
    vertices, _, normals = scan
    fit = fit_patch(vertices, normals, None, smoothing=1e-4, margin=2.0)
    face = TopoDS.Face(patch_face(fit.surface))
    surface = BRep_Tool.Surface_s(face)
    u0, u1, v0, v1 = fit.surface.domain
    point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surface.D1(0.5 * (u0 + u1), 0.5 * (v0 + v1), point, du, dv)
    normal = np.cross([du.X(), du.Y(), du.Z()], [dv.X(), dv.Y(), dv.Z()])
    assert float(normal @ normals.mean(axis=0)) > 0


def test_automatic_spans_reach_the_noise_level(
    scan: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> None:
    vertices, _, normals = scan
    fit = fit_patch(vertices, normals, None, smoothing=1e-4, margin=2.0)
    assert fit.rms <= 1.2 * SIGMA
    # About 5 mm spans over 80 x 60 mm plus the margin.
    assert 16 <= fit.surface.spans[0] <= 26 and 12 <= fit.surface.spans[1] <= 20


def test_margin_extends_the_patch(scan: tuple[np.ndarray, np.ndarray, np.ndarray]) -> None:
    vertices, _, normals = scan
    tight = fit_patch(vertices, normals, (16, 12), smoothing=1e-4, margin=0.0)
    wide = fit_patch(vertices, normals, (16, 12), smoothing=1e-4, margin=5.0)
    tight_u = tight.surface.domain[1] - tight.surface.domain[0]
    wide_u = wide.surface.domain[1] - wide.surface.domain[0]
    assert wide_u == pytest.approx(tight_u + 10.0, abs=1e-6)


def test_holes_in_the_scan_stay_well_posed() -> None:
    field = height_field_scan(sigma=SIGMA, seed=9)
    local = (field.vertices - field.offset) @ field.rotation
    keep = np.hypot(local[:, 0] + 25.0, local[:, 1] - 10.0) > 8.0
    normals = vertex_normals(field.vertices, field.faces)
    fit = fit_patch(field.vertices[keep], normals[keep], (16, 12), smoothing=1e-4, margin=2.0)
    assert fit.rms <= 1.2 * SIGMA
    # Over a 16 mm hole in the gently curved part the penalty bridges the gap smoothly.
    hole = field.vertices[~keep]
    error = np.abs(fit.surface.normal_distance(hole))
    assert float(np.percentile(error, 95)) < 0.1
    assert float(error.max()) < 0.2


def test_a_region_curved_beyond_150_degrees_is_rejected() -> None:
    angles = np.linspace(np.radians(-85.0), np.radians(85.0), 120)
    heights = np.linspace(0.0, 40.0, 60)
    aa, hh = np.meshgrid(angles, heights, indexing="ij")
    vertices = np.column_stack([10.0 * np.sin(aa.ravel()), hh.ravel(), 10.0 * np.cos(aa.ravel())])
    faces = grid_faces(len(angles), len(heights))
    normals = vertex_normals(vertices, faces)
    rng = np.random.default_rng(3)
    noisy = add_scanner_noise(vertices, normals, SIGMA, rng)
    with pytest.raises(KernelError) as raised:
        fit_patch(noisy, normals, None, smoothing=1e-4, margin=2.0)
    assert raised.value.code == ErrorCode.TOO_CURVED
    spread = raised.value.params["spreadDeg"]
    assert isinstance(spread, float) and spread > MAX_NORMAL_SPREAD_DEG
    # 120 degrees of the same cylinder is still a height field.
    narrow = np.abs(np.degrees(aa.ravel())) <= 60.0
    fit = fit_patch(noisy[narrow], normals[narrow], None, smoothing=1e-4, margin=0.0)
    assert fit.rms <= 1.5 * SIGMA
