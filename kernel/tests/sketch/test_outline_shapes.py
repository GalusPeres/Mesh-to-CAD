"""Outline shapes of section sketches: which shape an outline is, its design values,
the click fit, the fillet from the scan and painted lines (synthetic outlines)."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.sketch import fit2d
from m2c_kernel.sketch.api import fit_entity
from m2c_kernel.sketch.autofit import fit_points, fit_section
from m2c_kernel.sketch.convert import to_work
from m2c_kernel.sketch.fillet import fillet_corner
from m2c_kernel.sketch.gestures import fit_outline
from m2c_kernel.sketch.params import LineEntity, SketchParams, SketchPoint
from m2c_kernel.sketch.shape_entities import sizes
from m2c_kernel.sketch.shapes import choose
from tests.sketch.conftest import PLATE_SPEC, Outline, circle_points, section_of
from tests.timing import budget

SIGMA = 0.02
TOLERANCE = 0.1


def _slot(cx: float, cy: float, length: float, width: float, angle_deg: float = 0.0) -> Outline:
    r, a = width / 2, length / 2 - width / 2
    turn = math.radians(angle_deg)
    d = np.array([math.cos(turn), math.sin(turn)])
    n = np.array([-d[1], d[0]])
    c = np.array([cx, cy])

    def at(u: float, v: float) -> tuple[float, float]:
        p = c + u * d + v * n
        return float(p[0]), float(p[1])

    outline = Outline().line(at(-a, -r), at(a, -r))
    outline.arc(at(a, 0), r, angle_deg - 90, angle_deg + 90).line(at(a, r), at(-a, r))
    return outline.arc(at(-a, 0), r, angle_deg + 90, angle_deg + 270)


def _rounded_rect(length: float, width: float, corner: float) -> Outline:
    a, b = length / 2 - corner, width / 2 - corner
    hl, hw = length / 2, width / 2
    outline = Outline().line((-a, -hw), (a, -hw)).arc((a, -b), corner, -90, 0)
    outline.line((hl, -b), (hl, b)).arc((a, b), corner, 0, 90).line((a, hw), (-a, hw))
    return (
        outline.arc((-a, b), corner, 90, 180)
        .line((-hl, b), (-hl, -b))
        .arc((-a, -b), corner, 180, 270)
    )


def _ring_arm(inner: float, outer: float, gap: float) -> Outline:
    """The arm of a ring between rays at 45 and 135 degrees, ends `gap` off the rays."""
    u0, u1 = np.array([1.0, 1.0]) / math.sqrt(2), np.array([-1.0, 1.0]) / math.sqrt(2)
    n0, n1 = np.array([-u0[1], u0[0]]), np.array([u1[1], -u1[0]])

    def end(u: np.ndarray, n: np.ndarray, radius: float) -> tuple[float, float]:
        p = math.sqrt(radius**2 - gap**2) * u + gap * n
        return float(p[0]), float(p[1])

    def angle(p: tuple[float, float]) -> float:
        return math.degrees(math.atan2(p[1], p[0]))

    out0, out1 = end(u0, n0, outer), end(u1, n1, outer)
    in1, in0 = end(u1, n1, inner), end(u0, n0, inner)
    outline = Outline().arc((0, 0), outer, angle(out0), angle(out1)).line(out1, in1)
    return outline.arc((0, 0), inner, angle(in1), angle(in0)).line(in0, out0)


def _d_shape() -> Outline:
    """A circle cut by a chord: no simple shape."""
    start = (4 * math.cos(math.radians(-30)), 4 * math.sin(math.radians(-30)))
    end = (4 * math.cos(math.radians(210)), 4 * math.sin(math.radians(210)))
    return Outline().arc((0, 0), 4, -30, 210).line(end, start)


def _samples(outline: Outline, seed: int) -> np.ndarray:
    return fit2d.resample(outline.noisy(SIGMA, seed), 0.1, True)


@pytest.mark.parametrize(
    ("outline", "kind"),
    [
        (Outline().arc((0, 0), 5, 0, 360), "circle"),
        (_slot(0, 0, 20, 8), "slot"),
        (_rounded_rect(20, 12, 2), "roundedRect"),
        (_ring_arm(8, 14, 1.0), "ringArm"),
    ],
)
def test_each_shape_is_recognised(outline: Outline, kind: str) -> None:
    shape = choose(_samples(outline, 1), TOLERANCE)
    assert shape is not None and shape.kind == kind
    assert shape.rms < 2 * SIGMA


def test_a_circle_cut_by_a_chord_is_a_free_profile() -> None:
    assert choose(_samples(_d_shape(), 2), TOLERANCE) is None


def test_ring_arm_sizes_are_measured() -> None:
    shape = choose(_samples(_ring_arm(8, 14, 1.0), 3), TOLERANCE)
    assert shape is not None
    assert (shape["inner"], shape["outer"], shape["gap"]) == pytest.approx((8, 14, 1), abs=0.05)
    assert shape.center == pytest.approx((0, 0), abs=0.05)


def test_buttons_get_design_values_and_equal_sizes() -> None:
    first, second = _slot(0, 0, 8.0, 4.5), _slot(15, 0, 8.06, 4.5)
    section = section_of([first.noisy(SIGMA, 4), second.noisy(SIGMA, 5)])
    outcome = fit_section(section, TOLERANCE, "metric")
    sketch = outcome.sketch
    assert [s.kind for s in sketch.shapes] == ["slot", "slot"]
    for shape in sketch.shapes:
        assert sizes(sketch, shape) == pytest.approx({"width": 4.5, "length": 8.0}, abs=1e-6)
    kinds = [c.kind for c in outcome.constraints]
    assert kinds.count("horizontal") == 4 and kinds.count("tangent") == 8
    assert {s.kind for s in outcome.snaps} >= {"radius", "length"}


def test_an_oblique_slot_keeps_a_common_direction() -> None:
    section = section_of([_slot(0, 0, 20, 8, angle_deg=30.0).noisy(SIGMA, 6)])
    outcome = fit_section(section, TOLERANCE, "metric")
    angles = [s.value for s in outcome.snaps if s.kind == "angle"]
    assert angles == pytest.approx([30.0])


def test_constraints_stay_within_one_profile() -> None:
    left = _d_shape().noisy(SIGMA, 7)
    right = _d_shape().noisy(SIGMA, 8) + np.array([20.0, 0.0])
    holes = [circle_points((0, 20), 3, SIGMA, 9), circle_points((20, 20), 3, SIGMA, 10)]
    outcome = fit_section(section_of([left, right, *holes]), TOLERANCE, "metric")
    entities = outcome.sketch.entities
    for c in outcome.constraints:
        if c.kind == "equalRadius":
            assert all(entities[r].kind == "circle" for r in c.refs)
    assert [c.kind for c in outcome.constraints].count("equalRadius") == 1


def test_a_click_fits_the_outline_around_it_and_a_second_click_replaces_it() -> None:
    section = section_of(
        [_slot(0, 0, 20, 8).noisy(SIGMA, 11), circle_points((30, 0), 4, SIGMA, 12)]
    )
    params = SketchParams(section=PLATE_SPEC)
    first = fit_outline(params, section, np.array([0.0, 0.0]), "metric", TOLERANCE, SIGMA)
    assert first.kind == "slot" and len(first.entities) == 4
    again = fit_outline(first.params, section, np.array([1.0, 1.0]), "metric", TOLERANCE, SIGMA)
    assert len(again.params.entities) == 4 and len(again.params.shapes) == 1
    both = fit_outline(again.params, section, np.array([30.0, 0.5]), "metric", TOLERANCE, SIGMA)
    assert both.kind == "circle"
    assert len(both.params.entities) == 5
    circle = next(e for e in both.params.entities if e.id == both.entities[0])
    assert circle.radius == pytest.approx(4.0)  # type: ignore[union-attr]
    with pytest.raises(KernelError):
        fit_outline(both.params, section, np.array([60.0, 0.0]), "metric", TOLERANCE, SIGMA)


def _sharp_rectangle() -> SketchParams:
    corners = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
    points = [SketchPoint(id=f"p{k + 1}", x=x, y=y) for k, (x, y) in enumerate(corners)]
    lines = [
        LineEntity(id=f"e{k + 1}", start=f"p{k + 1}", end=f"p{(k + 1) % 4 + 1}") for k in range(4)
    ]
    return SketchParams(section=PLATE_SPEC, points=points, entities=lines)  # type: ignore[arg-type]


def test_a_corner_is_filleted_with_the_radius_of_the_scan() -> None:
    rounded = Outline().line((0, 0), (40, 0)).line((40, 0), (40, 17)).arc((37, 17), 3, 0, 90)
    rounded.line((37, 20), (0, 20)).line((0, 20), (0, 0))
    points = fit_points(section_of([rounded.noisy(SIGMA, 13)]))
    result = fillet_corner(_sharp_rectangle(), points, "p3", TOLERANCE, "metric")
    assert result.measured == pytest.approx(3.0, abs=0.1)
    assert result.radius == pytest.approx(3.0)
    sketch, constraints = to_work(result.params)
    arc = sketch.entities[result.entity]
    assert arc.center == pytest.approx((37, 17), abs=1e-6)  # type: ignore[union-attr]
    assert {c.refs for c in constraints if c.kind == "tangent"} == {
        ("e2", result.entity),
        (result.entity, "e3"),
    }
    assert sketch.xy(arc.start) == pytest.approx((40, 17), abs=1e-6)  # type: ignore[union-attr]


def test_a_sharp_scan_corner_has_nothing_to_fillet() -> None:
    sharp = Outline().line((0, 0), (40, 0)).line((40, 0), (40, 20)).line((40, 20), (0, 20))
    points = fit_points(section_of([sharp.line((0, 20), (0, 0)).noisy(SIGMA, 14)]))
    with pytest.raises(KernelError):
        fillet_corner(_sharp_rectangle(), points, "p3", TOLERANCE, "metric")


def test_a_painted_line_near_an_axis_becomes_horizontal() -> None:
    x = np.linspace(0, 30, 100)
    points = np.column_stack([x, 5 + x * math.tan(math.radians(0.3))])
    section = section_of([_slot(0, 0, 20, 8).noisy(SIGMA, 15)])
    params, entity, _ = fit_entity(SketchParams(section=PLATE_SPEC), section, points, "line")
    assert [(c.kind, c.refs) for c in params.constraints] == [("horizontal", [entity])]


def test_many_buttons_fit_quickly() -> None:
    buttons = [_slot(12 * (k % 4), 8 * (k // 4), 8.0, 4.5).noisy(SIGMA, 20 + k) for k in range(12)]
    start = time.perf_counter()
    outcome = fit_section(section_of(buttons), TOLERANCE, "metric")
    assert time.perf_counter() - start < budget(4.0)
    assert len(outcome.sketch.shapes) == 12
