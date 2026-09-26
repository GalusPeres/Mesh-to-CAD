"""Constraint inference and snapping on synthetic outlines; rotational sections."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from m2c_kernel.cad.occ_compat import (
    BRepAlgoAPI_Fuse,
    BRepPrimAPI_MakeCylinder,
    gp_Ax2,
    gp_Dir,
    gp_Pnt,
)
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.sketch.api import auto_fit, cut, evaluate, fit_entity, section_geometry
from m2c_kernel.sketch.autofit import fit_section
from m2c_kernel.sketch.model import Arc, Circle, Line
from m2c_kernel.sketch.params import (
    ArcEntity,
    LineEntity,
    RotationalSection,
    SketchDimension,
    SketchParams,
)
from tests.sketch.conftest import (
    PLATE_SPEC,
    Outline,
    circle_points,
    no_constructions,
    plate_section,
    section_of,
)
from tests.synthetic import add_scanner_noise
from tests.synthetic.parts import tessellate_part

SIGMA = 0.02


def _kinds(constraints: list) -> list[str]:  # type: ignore[type-arg]
    return sorted(c.kind for c in constraints)


def test_obround_has_four_tangent_junctions() -> None:
    obround = Outline().line((-20, -10), (20, -10)).arc((20, 0), 10, -90, 90)
    obround.line((20, 10), (-20, 10)).arc((-20, 0), 10, 90, 270)
    outcome = fit_section(section_of([obround.noisy(SIGMA, 3)]), None, "metric", snap=False)
    entities = list(outcome.sketch.entities.values())
    assert sorted(e.kind for e in entities) == ["arc", "arc", "line", "line"]
    assert _kinds(outcome.constraints).count("tangent") == 4
    radii = [e.radius for e in entities if isinstance(e, Arc)]
    assert radii == pytest.approx([10, 10], abs=0.01)


def test_obround_started_mid_arc_gives_the_same_topology() -> None:
    obround = Outline().arc((20, 0), 10, 0, 90).line((20, 10), (-20, 10))
    obround.arc((-20, 0), 10, 90, 270).line((-20, -10), (20, -10)).arc((20, 0), 10, -90, 0)
    outcome = fit_section(section_of([obround.noisy(SIGMA, 4)]), None, "metric", snap=False)
    assert sorted(e.kind for e in outcome.sketch.entities.values()) == [
        "arc",
        "arc",
        "line",
        "line",
    ]
    assert _kinds(outcome.constraints).count("tangent") == 4


def test_s_curve_tangencies_and_the_cusp() -> None:
    # Right edge, then an S of two R15 arcs touching at (30, 30), then down the left
    # edge: the second arc arrives going up while the left edge goes down (a cusp).
    shape = Outline().line((0, 0), (60, 0)).line((60, 0), (60, 30))
    shape.arc((45, 30), 15, 0, 180).arc((15, 30), 15, 0, -180).line((0, 30), (0, 0))
    outcome = fit_section(section_of([shape.noisy(SIGMA, 5)]), None, "metric", snap=False)
    entities = outcome.sketch.entities
    arcs = [e for e in entities.values() if isinstance(e, Arc)]
    assert len(entities) == 5 and len(arcs) == 2
    tangent = [set(c.refs) for c in outcome.constraints if c.kind == "tangent"]
    right = next(
        e for e in entities.values() if isinstance(e, Line) and abs(abs(e.offset) - 60) < 0.5
    )
    left = next(
        e
        for e in entities.values()
        if isinstance(e, Line) and abs(e.offset) < 0.5 and abs(e.normal[0]) > 0.9
    )
    assert {arcs[0].id, arcs[1].id} in tangent
    assert any(right.id in pair for pair in tangent)
    assert not any(left.id in pair for pair in tangent)
    assert len(tangent) == 2
    assert [a.radius for a in arcs] == pytest.approx([15, 15], abs=0.01)


def test_rotated_rectangle_gets_two_parallel_and_one_perpendicular() -> None:
    angle = math.radians(17.0)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    corners = [tuple(rotation @ np.array(c)) for c in ((0, 0), (40, 0), (40, 20), (0, 20))]
    rectangle = Outline()
    for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
        rectangle.line(a, b)  # type: ignore[arg-type]
    outcome = fit_section(section_of([rectangle.noisy(SIGMA, 6)]), None, "metric")
    assert len(outcome.sketch.entities) == 4
    assert _kinds(outcome.constraints) == ["parallel", "parallel", "perpendicular"]
    directions = [
        math.degrees((e.angle + math.pi / 2) % math.pi)
        for e in outcome.sketch.entities.values()
        if isinstance(e, Line)
    ]
    assert min(directions) == pytest.approx(17.0, abs=0.05)


def test_holes_on_a_bolt_circle_snap_with_equal_pitch() -> None:
    square = Outline().line((-50, -50), (50, -50)).line((50, -50), (50, 50))
    square.line((50, 50), (-50, 50)).line((-50, 50), (-50, -50))
    holes = [
        circle_points(
            (30 * math.cos(math.radians(a)), 30 * math.sin(math.radians(a))), 4, SIGMA, 10 + k
        )
        for k, a in enumerate((45, 135, 225, 315))
    ]
    shifted = [h + np.array([0.004, -0.003]) for h in holes]
    outcome = fit_section(section_of([square.noisy(SIGMA, 7), *shifted]), None, "metric")
    bolt = [s for s in outcome.snaps if s.kind == "boltCircle"]
    assert len(bolt) == 1
    assert bolt[0].value == pytest.approx(60.0)
    assert bolt[0].pitch_deg == pytest.approx(90.0)
    assert bolt[0].start_deg is not None and bolt[0].start_deg % 90 == pytest.approx(45.0)
    circles = [e for e in outcome.sketch.entities.values() if isinstance(e, Circle)]
    for circle in circles:
        assert float(np.linalg.norm(circle.center)) == pytest.approx(30.0, abs=1e-4)
        assert circle.radius == pytest.approx(4.0, abs=1e-4)


def _stepped_shaft() -> tuple[np.ndarray, np.ndarray]:
    up = gp_Dir(0, 0, 1)
    shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), up), 10.0, 30.0).Shape()
    for z, radius, height in ((30.0, 7.5, 20.0), (50.0, 5.0, 15.0)):
        step = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z), up), radius, height).Shape()
        shape = BRepAlgoAPI_Fuse(shape, step).Shape()
    part = tessellate_part(shape, 1.0)
    rng = np.random.default_rng(21)
    vertices = add_scanner_noise(
        part.vertices, vertex_normals(part.vertices, part.faces), SIGMA, rng
    )
    return vertices, part.faces


@pytest.mark.occt
def test_rotational_section_of_a_stepped_shaft_gives_exact_radii() -> None:
    vertices, faces = _stepped_shaft()
    spec = RotationalSection(axis="Z")
    geometry = section_geometry(spec, no_constructions)  # type: ignore[arg-type]
    section = cut(vertices, faces, geometry)
    assert section.rotational and section.support is not None
    result = auto_fit(SketchParams(section=spec), section, "metric", refit=False)
    params = result.params
    points = {p.id: (p.x, p.y) for p in params.points}
    lines = [e for e in params.entities if isinstance(e, LineEntity)]
    along_axis = sorted(
        round(points[e.start][1], 6)
        for e in lines
        if abs(points[e.start][1] - points[e.end][1]) < 1e-4
    )
    # The three shaft surfaces plus the closing line on the axis.
    assert along_axis == pytest.approx([0.0, 5.0, 7.5, 10.0], abs=1e-4)
    shoulders = sorted(
        round(points[e.start][0], 6)
        for e in lines
        if abs(points[e.start][0] - points[e.end][0]) < 1e-4
    )
    assert shoulders == pytest.approx([0.0, 30.0, 50.0, 65.0], abs=1e-4)
    assert [e.origin for e in lines].count("axis") == 1
    assert result.profile.closed
    faces_out = evaluate(params, geometry).profiles.profile_faces
    assert len(faces_out) == 1


def test_typed_dimension_is_kept_by_the_refit() -> None:
    _, section = plate_section(0.02)
    fitted = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    notch = next(
        e for e in fitted.entities if isinstance(e, ArcEntity) and abs(e.radius - 10) < 0.5
    )
    edited = replace(
        fitted,
        snaps=[s for s in fitted.snaps if s.entity != notch.id],
        dimensions=[SketchDimension(entity=notch.id, kind="radius", value=9.0)],
    )
    refitted = auto_fit(edited, section, "metric", refit=True).params
    arc = next(e for e in refitted.entities if e.id == notch.id)
    assert isinstance(arc, ArcEntity)
    assert arc.radius == pytest.approx(9.0, abs=1e-5)
    points = {p.id: np.array([p.x, p.y]) for p in refitted.points}
    for end in (arc.start, arc.end):
        assert float(np.linalg.norm(points[end] - np.array(arc.center))) == pytest.approx(
            9.0, abs=1e-5
        )
        assert points[end][1] == pytest.approx(30.0, abs=1e-4)  # still on the top edge
    assert refitted.dimensions == edited.dimensions


def test_profile_opens_when_an_entity_is_deleted() -> None:
    geometry, section = plate_section(0.02)
    fitted = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    y = {p.id: p.y for p in fitted.points}
    bottom = next(
        e
        for e in fitted.entities
        if isinstance(e, LineEntity)
        and y[e.start] == pytest.approx(-30)
        and y[e.end] == pytest.approx(-30)
    )
    remaining = replace(fitted, entities=[e for e in fitted.entities if e.id != bottom.id])
    result = evaluate(remaining, geometry)
    assert len(result.profile.gaps) == 2
    assert len(result.profiles.profile_faces) == 2  # the two holes stay closed
    assert bottom.id not in result.profile.open_entities


def test_fit_entity_through_painted_points() -> None:
    _, section = plate_section(0.02)
    fitted = auto_fit(SketchParams(section=PLATE_SPEC), section, "metric", refit=False).params
    loop = max(section.loops, key=len)
    painted = loop[(loop[:, 0] > -40) & (loop[:, 0] < 40) & (loop[:, 1] < -29)]
    params, entity_id, max_distance = fit_entity(fitted, section, painted, "auto")
    added = next(e for e in params.entities if e.id == entity_id)
    assert isinstance(added, LineEntity) and added.origin == "fit"
    assert max_distance < 0.1
    assert len(params.points) == len(fitted.points) + 2
    hole = next(p for p in section.loops if np.linalg.norm(p.mean(axis=0) - [25, -5]) < 1)
    arc_params, arc_id, _ = fit_entity(fitted, section, hole[: len(hole) // 3], "arc")
    arc = next(e for e in arc_params.entities if e.id == arc_id)
    assert isinstance(arc, ArcEntity) and arc.radius == pytest.approx(6.0, abs=0.05)
