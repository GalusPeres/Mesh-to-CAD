"""Section sketch of the test plate: topology, accuracy, snapping, profile, speed."""

from __future__ import annotations

import time

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import BRepGProp, BRepPrimAPI_MakePrism, GProp_GProps, gp_Vec
from m2c_kernel.protocol.wire import from_json, to_json
from m2c_kernel.sketch.api import auto_fit, evaluate, section_geometry
from m2c_kernel.sketch.autofit import FitOutcome, fit_section
from m2c_kernel.sketch.model import Arc, Circle, Line
from m2c_kernel.sketch.params import ArcEntity, CircleEntity, LineEntity, SketchParams
from tests.sketch.conftest import (
    PLATE_CORNERS,
    PLATE_SPEC,
    no_constructions,
    noisy_plate,
    plate_section,
)
from tests.synthetic.parts import build_test_plate
from tests.timing import budget

pytestmark = pytest.mark.occt


def _corner_error(points: np.ndarray) -> float:
    return max(float(np.min(np.linalg.norm(points - c, axis=1))) for c in PLATE_CORNERS)


def _measured(sigma: float) -> FitOutcome:
    _, section = plate_section(sigma)
    return fit_section(section, None, "metric", snap=False)


def test_plate_topology_and_accuracy_at_sigma_002() -> None:
    outcome = _measured(0.02)
    entities = list(outcome.sketch.entities.values())
    circles = [e for e in entities if isinstance(e, Circle)]
    outline = [e for e in entities if not isinstance(e, Circle)]
    assert len(outline) == 10
    assert len(circles) == 2
    assert sorted(e.kind for e in outline) == ["arc"] * 4 + ["line"] * 6

    points = np.array([p.xy for p in outcome.sketch.points.values()])
    assert len(points) == 10
    assert _corner_error(points) < 0.03

    radii = sorted(e.radius for e in entities if isinstance(e, Arc | Circle))
    assert radii == pytest.approx([6, 6, 8, 8, 8, 10], abs=0.005)
    assert 0.01 < outcome.noise < 0.03
    assert outcome.tolerance == pytest.approx(max(6 * outcome.noise, 0.05))


def test_plate_corners_at_sigma_005() -> None:
    outcome = _measured(0.05)
    assert len(outcome.sketch.entities) == 12
    points = np.array([p.xy for p in outcome.sketch.points.values()])
    assert _corner_error(points) < 0.06


def test_snapped_plate_is_exact() -> None:
    _, section = plate_section(0.02)
    result = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False)
    params = result.params
    points = {p.id: np.array([p.x, p.y]) for p in params.points}
    exact = 1e-4

    lines = [e for e in params.entities if isinstance(e, LineEntity)]
    lengths = sorted(
        round(float(np.linalg.norm(points[e.end] - points[e.start])), 6) for e in lines
    )
    # Bottom 84, right 44, two top edges 32 beside the notch, left 44, chamfer 8 * sqrt(2).
    assert lengths == pytest.approx([8 * np.sqrt(2), 32, 32, 44, 44, 84], abs=exact)
    assert _corner_error(np.array(list(points.values()))) < exact

    arcs = [e for e in params.entities if isinstance(e, ArcEntity)]
    assert sorted(e.radius for e in arcs) == pytest.approx([8, 8, 8, 10], abs=exact)
    notch = next(e for e in arcs if abs(e.radius - 10) < 1)
    assert notch.center == pytest.approx((0, 30), abs=exact)

    holes = sorted(
        (e for e in params.entities if isinstance(e, CircleEntity)), key=lambda e: e.center[0]
    )
    assert [h.radius for h in holes] == pytest.approx([6, 6], abs=exact)
    assert holes[0].center == pytest.approx((-25, -5), abs=exact)
    assert holes[1].center == pytest.approx((25, -5), abs=exact)

    snapped = {s.kind for s in params.snaps}
    assert {"radius", "x", "y", "angle", "centerX", "centerY", "junction"} <= snapped
    for snap in params.snaps:
        assert abs(snap.value - snap.measured) <= max(3 * snap.uncertainty, 0.05)
    assert all(f.passed for f in result.fits)
    assert result.profile.closed
    assert len(result.profile.loops) == 3


def test_constraints_of_the_plate() -> None:
    constraints = _measured(0.02).constraints
    kinds = sorted(c.kind for c in constraints)
    assert kinds.count("horizontal") == 3
    assert kinds.count("vertical") == 2
    assert kinds.count("collinear") == 1
    assert kinds.count("tangent") == 6
    assert kinds.count("equalRadius") == 3


def test_extruded_profile_matches_the_true_volume() -> None:
    geometry, section = plate_section(0.02)
    params = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    result = evaluate(params, geometry)
    assert len(result.profiles.profile_faces) == 1
    prism = BRepPrimAPI_MakePrism(result.profiles.profile_faces[0], gp_Vec(0, 0, 10)).Shape()
    measured, truth = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(prism, measured)
    BRepGProp.VolumeProperties_s(build_test_plate(), truth)
    assert abs(measured.Mass() - truth.Mass()) / truth.Mass() < 1e-4
    names = result.profiles.edge_names[0]
    assert sorted(names) == sorted(e.id for e in params.entities)
    assert set(result.profiles.lines) == {
        e.id for e in params.entities if isinstance(e, LineEntity)
    }


def test_sketch_json_round_trip() -> None:
    _, section = plate_section(0.02)
    params = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    encoded = to_json(params, SketchParams)
    assert from_json(encoded, SketchParams) == params
    assert to_json(from_json(encoded, SketchParams), SketchParams) == encoded


def test_refit_keeps_snaps_and_is_stable() -> None:
    _, section = plate_section(0.02)
    first = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    second = auto_fit(first, section, "metric", refit=True).params
    assert [e.id for e in second.entities] == [e.id for e in first.entities]
    assert second.snaps == first.snaps
    before = {p.id: (p.x, p.y) for p in first.points}
    for point in second.points:
        assert (point.x, point.y) == pytest.approx(before[point.id], abs=1e-4)


def test_section_and_fit_are_fast() -> None:
    scan = noisy_plate(0.02)
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        geometry = section_geometry(PLATE_SPEC, no_constructions)  # type: ignore[arg-type]
        section = scan.section(geometry)
        auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False)
        timings.append(time.perf_counter() - start)
    assert min(timings) < budget(0.3)


def test_measured_values_without_snapping() -> None:
    entities = _measured(0.02).sketch.entities.values()
    lines = [e for e in entities if isinstance(e, Line)]
    offsets = sorted(abs(e.offset) for e in lines if abs(abs(e.normal[0]) - 1) < 1e-6)
    assert offsets == pytest.approx([50, 50], abs=0.01)
