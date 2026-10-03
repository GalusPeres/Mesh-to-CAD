"""Every plane and cylinder of the test block, fitted from its ground-truth triangles.

The block (1 mm triangles, 939k faces) is scanned with sigma 0.03 mm noise and
0.1 % spikes in its design position (as after an exact alignment). Free fits must
meet the accuracy targets of ARCHITECTURE.md 1.5. The boss cylinder is only
10 mm tall; its axis cannot be determined to 0.01 degrees from this noise, so
axis errors may also be up to three reported standard uncertainties (which must
themselves stay small). With snapping, the design values come out exactly.
"""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.api import Cylinder, FitRequest, Plane, run_fit
from m2c_kernel.mesh.normals import vertex_normals
from tests.fitting.helpers import SIGMA, angle_deg, line_distance
from tests.synthetic import add_scanner_noise
from tests.synthetic.parts import SyntheticPart, block_part

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def scanned() -> tuple[SyntheticPart, EvalMesh]:
    part = block_part()
    rng = np.random.default_rng(17)
    normals = vertex_normals(part.vertices, part.faces)
    noisy = add_scanner_noise(part.vertices, normals, SIGMA, rng, spike_fraction=0.001)
    return part, EvalMesh("mesh:block", noisy, part.faces, None)


def _faces_of(part: SyntheticPart, kind: type) -> list[int]:
    return [index for index, surface in enumerate(part.surfaces) if isinstance(surface, kind)]


def test_planes_meet_the_targets(scanned: tuple[SyntheticPart, EvalMesh]) -> None:
    part, mesh = scanned
    for index in _faces_of(part, Plane):
        truth = part.surfaces[index]
        assert isinstance(truth, Plane)
        faces = np.nonzero(part.labels == index)[0]
        outcome = run_fit(
            mesh, faces, FitRequest(kind="plane", snap=False), np.random.default_rng(index)
        )
        fit = outcome.primitive
        assert isinstance(fit, Plane)
        assert angle_deg(fit.normal, truth.normal) < 0.01, index
        offset = float(
            (np.asarray(fit.origin) - np.asarray(truth.origin)) @ np.asarray(truth.normal)
        )
        assert abs(offset) < 0.005, index
        assert np.dot(fit.normal, truth.normal) > 0, index


def test_cylinders_meet_the_targets(scanned: tuple[SyntheticPart, EvalMesh]) -> None:
    part, mesh = scanned
    for index in _faces_of(part, Cylinder):
        truth = part.surfaces[index]
        assert isinstance(truth, Cylinder)
        faces = np.nonzero(part.labels == index)[0]
        outcome = run_fit(
            mesh, faces, FitRequest(kind="auto", snap=False), np.random.default_rng(index)
        )
        fit = outcome.primitive
        assert isinstance(fit, Cylinder), (index, fit)
        # Two direction parameters: the angle error is their combined deviation.
        spread = 3.0 * np.sqrt(2.0) * outcome.stats.uncertainty["direction"]
        assert outcome.stats.uncertainty["direction"] < 0.01, index
        assert angle_deg(fit.axis, truth.axis) < max(0.01, spread), index
        assert abs(fit.radius - truth.radius) < 0.01, index
        assert line_distance(fit.origin, truth.origin, truth.axis) < 0.01, index
        # The D16 through hole is the only concave cylinder.
        assert outcome.stats.concave is (truth.radius == 8.0), index


def test_snapping_recovers_the_design_values(scanned: tuple[SyntheticPart, EvalMesh]) -> None:
    part, mesh = scanned
    for index in _faces_of(part, Plane) + _faces_of(part, Cylinder):
        truth = part.surfaces[index]
        faces = np.nonzero(part.labels == index)[0]
        outcome = run_fit(mesh, faces, FitRequest(kind="auto"), np.random.default_rng(index))
        fit = outcome.primitive
        if isinstance(truth, Plane):
            assert isinstance(fit, Plane)
            assert np.abs(fit.normal).tolist() == np.abs(truth.normal).tolist(), index
            design = float(np.dot(truth.origin, truth.normal))
            assert float(np.dot(fit.origin, fit.normal)) == pytest.approx(design, abs=1e-9)
        else:
            assert isinstance(fit, Cylinder) and isinstance(truth, Cylinder)
            assert fit.axis == (0.0, 0.0, 1.0), index
            assert fit.radius == truth.radius, index
        assert outcome.stats.passed, index
