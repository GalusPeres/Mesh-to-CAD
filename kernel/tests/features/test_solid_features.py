"""Solid feature types evaluated through the rebuild engine, against exact volumes."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from m2c_kernel.document.model import Document, Feature
from m2c_kernel.document.rebuild import RebuildResult, rebuild
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.features.helpers import document, feature, rect, scan_of, upstream_test_types
from tests.synthetic import add_scanner_noise, primitive_patch
from tests.timing import budget

pytestmark = pytest.mark.occt

EXACT = 1e-3  # mm^3


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    with upstream_test_types():
        yield


def _run(session: Session, job: JobContext, doc: Document) -> RebuildResult:
    return rebuild(doc, session.environment(), job)


def _volume(result: RebuildResult, body: str) -> float:
    return result.body_checks[body].volume


def _error(result: RebuildResult, feature_id: str) -> tuple[str, dict[str, Any]]:
    status = result.statuses[feature_id]
    assert status.state == "error", status
    assert status.error is not None
    return status.error.code, dict(status.error.params)


def _plate_sketch(feature_id: str = "f1", **extra: Any) -> Feature:
    return feature(feature_id, "testSketch", rects=[rect("l1", 0, 0, 40, 20)], **extra)


def _extrude(feature_id: str, sketch: str = "f1", **params: Any) -> Feature:
    params.setdefault("extent", {"type": "distance", "forward": 10.0})
    return feature(feature_id, "extrude", sketch=sketch, **params)


# --- Extrude -----------------------------------------------------------------------------------


def test_extrude_new_body_is_named_after_the_feature(session: Session, job: JobContext) -> None:
    result = _run(session, job, document(_plate_sketch(), _extrude("f2")))
    assert result.statuses["f2"].state == "ok"
    assert list(result.bodies) == ["f2"]
    assert _volume(result, "f2") == pytest.approx(8000.0, abs=EXACT)
    assert sorted(result.bodies["f2"].face_tags) == sorted(
        ["f2:cap:start", "f2:cap:end"] + [f"f2:side:l1e{k}" for k in range(4)]
    )


def test_extrude_both_sides_symmetric_and_reversed(session: Session, job: JobContext) -> None:
    both = {"type": "distance", "forward": 10.0, "backward": 5.0}
    doc = document(
        _plate_sketch(),
        _extrude("f2", extent=both),
        _extrude("f3", extent={"type": "distance", "forward": 15.0}, direction="symmetric"),
        _extrude("f4", extent={"type": "distance", "forward": 6.0}, direction="reversed"),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(12000.0, abs=EXACT)
    assert _volume(result, "f3") == pytest.approx(12000.0, abs=EXACT)
    assert _volume(result, "f4") == pytest.approx(4800.0, abs=EXACT)
    from m2c_kernel.cad.profiles import shape_vertices

    symmetric = shape_vertices(result.bodies["f3"].shape)
    assert symmetric[:, 2].min() == pytest.approx(-7.5)
    assert symmetric[:, 2].max() == pytest.approx(7.5)
    assert shape_vertices(result.bodies["f4"].shape)[:, 2].min() == pytest.approx(-6.0)


def test_extrude_up_to_planes(session: Session, job: JobContext) -> None:
    tilted = feature(
        "f2", "testConstruction", kind="plane", origin=(0, 0, 8.0), direction=(0, -0.1, 1)
    )
    doc = document(
        _plate_sketch(),
        tilted,
        _extrude("f3", extent={"type": "toPlane", "feature": "f2"}),
        _extrude("f4", extent={"type": "toPlane", "feature": "XY", "offset": 4.0}),
        _extrude("f5", extent={"type": "toPlane", "feature": "XY"}, direction="symmetric"),
    )
    result = _run(session, job, doc)
    # z = 8 + 0.1 y over y in [0, 20]: mean height 9.
    assert _volume(result, "f3") == pytest.approx(40 * 20 * 9.0, abs=EXACT)
    assert _volume(result, "f4") == pytest.approx(40 * 20 * 4.0, abs=EXACT)
    assert _error(result, "f5")[0] == "cad.symmetricToPlane"


def test_extrude_selected_loops_and_missing_loops(session: Session, job: JobContext) -> None:
    sketch = feature("f1", "testSketch", rects=[rect("l1", 0, 0, 10, 10), rect("l2", 20, 0, 5, 5)])
    doc = document(
        sketch,
        _extrude("f2", loops=["l2"]),
        _extrude("f3", loops=["l9"]),
        _extrude("f4"),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(250.0, abs=EXACT)
    assert _error(result, "f3") == ("cad.loopNotFound", {"loop": "l9"})
    # Two separate islands cannot be one body.
    assert _error(result, "f4")[0] == "cad.noOverlap"


def test_extrude_without_entity_names_names_edges_by_loop(
    session: Session, job: JobContext
) -> None:
    result = _run(session, job, document(_plate_sketch(named=False), _extrude("f2")))
    assert "f2:side:l1.0" in result.bodies["f2"].face_tags


def test_extrude_operations_change_the_target_body(session: Session, job: JobContext) -> None:
    pocket = feature("f3", "testSketch", rects=[rect("p", 10, 5, 10, 10)])
    doc = document(
        _plate_sketch(),
        _extrude("f2"),
        pocket,
        _extrude(
            "f4",
            sketch="f3",
            extent={"type": "distance", "forward": 4.0},
            operation="cut",
            target_body="f2",
            direction="symmetric",
        ),
        _extrude(
            "f5",
            sketch="f3",
            extent={"type": "distance", "forward": 15.0},
            operation="add",
            target_body="f2",
        ),
        _extrude("f6", sketch="f3", operation="add"),
    )
    result = _run(session, job, doc)
    assert list(result.bodies) == ["f2"]
    assert result.body_owner["f2"] == "f5"
    # Cut z = 0..2 from the pocket column, then fill the column up to z = 15.
    assert _volume(result, "f2") == pytest.approx(8000 - 1000 + 1500, abs=EXACT)
    assert _error(result, "f6") == ("cad.targetRequired", {"operation": "add"})


def test_separate_profiles_join_and_cut_the_target_together(
    session: Session, job: JobContext
) -> None:
    # Two buttons on the plate and two holes through it, one feature each.
    pair = feature("f3", "testSketch", rects=[rect("a", 5, 5, 5, 5), rect("b", 25, 5, 5, 5)])
    holes = feature("f5", "testSketch", rects=[rect("c", 12, 12, 2, 2), rect("d", 30, 12, 2, 2)])
    doc = document(
        _plate_sketch(),
        _extrude("f2"),
        pair,
        _extrude(
            "f4",
            sketch="f3",
            extent={"type": "distance", "forward": 12.0, "backward": 1.0},
            operation="add",
            target_body="f2",
        ),
        holes,
        _extrude("f6", sketch="f5", operation="cut", target_body="f2"),
    )
    result = _run(session, job, doc)
    assert result.statuses["f4"].state == "ok"
    assert result.statuses["f6"].state == "ok"
    assert result.body_checks["f2"].solids == 1
    # Each button stands 2 above and 1 below the plate (z = -1..12); the holes go through.
    assert _volume(result, "f2") == pytest.approx(8000 + 2 * 25 * 3 - 2 * 4 * 10, abs=EXACT)


def test_extrude_intersect_keeps_the_common_part(session: Session, job: JobContext) -> None:
    cross = feature("f3", "testSketch", rects=[rect("c", 30, -5, 20, 30)])
    doc = document(
        _plate_sketch(),
        _extrude("f2"),
        cross,
        _extrude(
            "f4",
            sketch="f3",
            extent={"type": "distance", "forward": 3.0},
            operation="intersect",
            target_body="f2",
        ),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(10 * 20 * 3, abs=EXACT)


# --- Revolve -----------------------------------------------------------------------------------


def _ring_sketch(**extra: Any) -> Feature:
    return feature("f1", "testSketch", plane="XZ", rects=[rect("r", 10, 0, 10, 30)], **extra)


def test_revolve_about_global_feature_and_sketch_axes(session: Session, job: JobContext) -> None:
    axis = feature("f2", "testConstruction", kind="cylinder", origin=(0, 0, -3.0), radius=1.0)
    reference = feature("f3", "testConstruction", kind="axis", origin=(0, 0, 5.0))
    doc = document(
        _ring_sketch(axis_line=((0.0, 0.0), (0.0, 40.0))),
        axis,
        reference,
        feature("f4", "revolve", sketch="f1", axis={"type": "globalAxis", "axis": "Z"}),
        feature("f5", "revolve", sketch="f1", axis={"type": "featureAxis", "feature": "f2"}),
        feature(
            "f6",
            "revolve",
            sketch="f1",
            axis={"type": "featureAxis", "feature": "f3"},
            angleDeg=90.0,
        ),
        feature("f7", "revolve", sketch="f1", axis={"type": "sketchLine", "entity": "a0"}),
        feature("f8", "revolve", sketch="f1", axis={"type": "sketchLine", "entity": "missing"}),
    )
    result = _run(session, job, doc)
    for body in ("f4", "f5", "f7"):
        assert _volume(result, body) == pytest.approx(28274.334, abs=EXACT)
    assert _volume(result, "f6") == pytest.approx(28274.334 / 4, abs=EXACT)
    assert {"f6:cap:start", "f6:cap:end"} <= set(result.bodies["f6"].face_tags)
    assert sorted(set(result.bodies["f4"].face_tags)) == [f"f4:rev:re{k}" for k in range(4)]
    assert _error(result, "f8") == ("cad.axisNotFound", {"entity": "missing"})


def test_revolve_uses_a_profile_edge_as_axis(session: Session, job: JobContext) -> None:
    # Half section of a shaft: the edge on the Z axis is edge 3 of the loop (x = 0).
    shaft = feature("f1", "testSketch", plane="XZ", rects=[rect("s", 0, 0, 6, 20)])
    doc = document(
        shaft, feature("f2", "revolve", sketch="f1", axis={"type": "sketchLine", "entity": "se3"})
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(math.pi * 36 * 20, abs=EXACT)


def test_revolve_axis_crossing_the_profile_fails(session: Session, job: JobContext) -> None:
    doc = document(
        feature("f1", "testSketch", plane="XZ", rects=[rect("r", -5, 0, 10, 10)]),
        feature("f2", "revolve", sketch="f1", axis={"type": "globalAxis", "axis": "Z"}),
    )
    assert _error(_run(session, job, doc), "f2")[0] == "cad.axisCrossesProfile"


# --- Primitive bodies --------------------------------------------------------------------------


def test_closed_primitives_are_exact(session: Session, job: JobContext) -> None:
    doc = document(
        feature("f1", "testConstruction", kind="sphere", origin=(1, 2, 3), radius=7.0),
        feature("f2", "testConstruction", kind="plane"),
        feature("f3", "primitiveBody", fit="f1"),
        feature("f4", "primitiveBody", fit="f2"),
        feature(
            "f5", "testConstruction", kind="torus", direction=(0, 1, 1), radius=20.0, minor=3.0
        ),
        feature("f6", "primitiveBody", fit="f5"),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f3") == pytest.approx(4 / 3 * math.pi * 343, abs=EXACT)
    assert set(result.bodies["f3"].face_tags) == {"f3:surface"}
    assert _error(result, "f4") == ("cad.unsupportedFit", {"feature": "f2"})
    assert _volume(result, "f6") == pytest.approx(2 * math.pi**2 * 20 * 9, abs=EXACT)


def test_manual_extent_counts_from_the_origin_foot(session: Session, job: JobContext) -> None:
    doc = document(
        feature("f1", "testConstruction", kind="cylinder", origin=(5, 5, -40.0), radius=4.0),
        feature(
            "f2", "primitiveBody", fit="f1", extent={"type": "manual", "start": 2.0, "length": 10.0}
        ),
        feature("f3", "testConstruction", kind="cone", origin=(0, 0, 0.0), half_angle_deg=30.0),
        feature(
            "f4",
            "primitiveBody",
            fit="f3",
            extent={"type": "manual", "start": -5.0, "length": 15.0},
        ),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(math.pi * 16 * 10, abs=EXACT)
    from m2c_kernel.cad.profiles import shape_vertices

    z = shape_vertices(result.bodies["f2"].shape)[:, 2]
    assert z.min() == pytest.approx(2.0)
    assert z.max() == pytest.approx(12.0)
    # The cone starts at its apex even though the range begins 5 mm before it.
    top = 10 * math.tan(math.radians(30.0))
    assert _volume(result, "f4") == pytest.approx(math.pi * top**2 * 10 / 3, abs=EXACT)


def test_region_extent_follows_the_scan_surface(session: Session, job: JobContext) -> None:
    rng = np.random.default_rng(7)
    patch = primitive_patch("cylinder", math.radians(120), 30.0, resolution=120, radius=8.0)
    noisy = add_scanner_noise(patch.vertices, patch.normals, 0.03, rng, spike_fraction=0.001)
    scan = scan_of(session, noisy, patch.faces)
    doc = document(
        feature("f1", "testConstruction", kind="cylinder", radius=8.0, covered=(-16.5, 16.5)),
        feature("f2", "primitiveBody", fit="f1", extent={"type": "region", "margin": 1.0}),
        scan=scan,
    )
    result = _run(session, job, doc)
    assert result.statuses["f2"].state == "ok"
    # The patch spans z = -15..15; spikes beyond the tolerance are ignored.
    from m2c_kernel.cad.profiles import shape_vertices

    z = shape_vertices(result.bodies["f2"].shape)[:, 2]
    assert z.min() == pytest.approx(-16.0, abs=0.05)
    assert z.max() == pytest.approx(16.0, abs=0.05)
    # The seam lies opposite the covered arc (centred on +X).
    assert shape_vertices(result.bodies["f2"].shape)[:, 0].min() == pytest.approx(-8.0, abs=1e-6)


def test_cone_region_extent(session: Session, job: JobContext) -> None:
    rng = np.random.default_rng(11)
    # Cone with apex at the origin, 30 degrees, covered from z = 10 to z = 30.
    patch = primitive_patch("cone", 2 * math.pi, 20.0, resolution=150, apex_distance=20.0)
    noisy = add_scanner_noise(patch.vertices, patch.normals, 0.03, rng)
    doc = document(
        feature("f1", "testConstruction", kind="cone", half_angle_deg=30.0, covered=(9.0, 31.0)),
        feature("f2", "primitiveBody", fit="f1"),
        scan=scan_of(session, noisy, patch.faces),
    )
    result = _run(session, job, doc)
    slope = math.tan(math.radians(30.0))
    frustum = math.pi * 20 / 3 * ((10 * slope) ** 2 + 10 * slope * 30 * slope + (30 * slope) ** 2)
    assert _volume(result, "f2") == pytest.approx(frustum, rel=5e-4)


def test_region_extent_needs_scan_points(session: Session, job: JobContext) -> None:
    patch = primitive_patch("plane", 20.0, 20.0, resolution=20)
    doc = document(
        feature("f1", "testConstruction", kind="cylinder", radius=8.0, covered=(5.0, 10.0)),
        feature("f2", "primitiveBody", fit="f1"),
        scan=scan_of(session, patch.vertices, patch.faces),
    )
    assert _error(_run(session, job, doc), "f2") == ("cad.noExtent", {"feature": "f1"})


# --- Trim and combine --------------------------------------------------------------------------


def test_trim_sphere_by_a_tilted_plane(session: Session, job: JobContext) -> None:
    plane = feature(
        "f2", "testConstruction", kind="plane", origin=(0, 0, 4.0), direction=(0, 0.2, 1)
    )
    doc = document(
        feature("f1", "testConstruction", kind="sphere", radius=10.0),
        plane,
        feature("f3", "primitiveBody", fit="f1"),
        feature(
            "f4", "trim", targetBody="f3", tool={"type": "plane", "feature": "f2"}, keep="front"
        ),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f3") == pytest.approx(925.353, abs=EXACT)
    assert result.body_owner["f3"] == "f4"
    assert "f4:split" in result.bodies["f3"].face_tags


def test_trim_by_origin_plane_and_errors(session: Session, job: JobContext) -> None:
    doc = document(
        _plate_sketch(),
        _extrude("f2", extent={"type": "distance", "forward": 10.0, "backward": 10.0}),
        feature("f3", "trim", targetBody="f2", tool={"type": "plane", "feature": "XY"}),
        feature("f4", "testConstruction", kind="sphere", radius=3.0),
        feature("f5", "trim", targetBody="f2", tool={"type": "plane", "feature": "f4"}),
        feature("f6", "trim", targetBody="f2", tool={"type": "patch", "feature": "f4"}),
    )
    result = _run(session, job, doc)
    assert _volume(result, "f2") == pytest.approx(8000.0, abs=EXACT)
    assert _error(result, "f5") == ("cad.notAPlane", {"feature": "f4"})
    assert _error(result, "f6") == ("cad.notAPatch", {"feature": "f4"})


def test_combine_operations_and_keep_tools(session: Session, job: JobContext) -> None:
    second = feature("f3", "testSketch", rects=[rect("b", 30, 5, 20, 10)])
    common = [_plate_sketch(), _extrude("f2"), second, _extrude("f4", sketch="f3")]

    def combined(operation: str, keep: bool = False) -> RebuildResult:
        combine = feature(
            "f5", "combine", targetBody="f2", tools=["f4"], operation=operation, keepTools=keep
        )
        return _run(session, job, document(*common, combine))

    added = combined("add")
    assert list(added.bodies) == ["f2"]
    assert _volume(added, "f2") == pytest.approx(8000 + 2000 - 1000, abs=EXACT)
    cut = combined("cut", keep=True)
    assert sorted(cut.bodies) == ["f2", "f4"]
    assert _volume(cut, "f2") == pytest.approx(7000.0, abs=EXACT)
    assert _volume(combined("intersect"), "f2") == pytest.approx(1000.0, abs=EXACT)
    itself = feature("f5", "combine", targetBody="f2", tools=["f2"], operation="add")
    assert _error(_run(session, job, document(*common, itself)), "f5")[0] == "cad.toolIsTarget"


# --- Fillet ------------------------------------------------------------------------------------


def _top_edges(tag: str = "f2") -> list[dict[str, Any]]:
    return [
        {"faces": [f"{tag}:cap:end", f"{tag}:side:l1e{k}"], "point": [0.0, 0.0, 0.0]}
        for k in range(4)
    ]


def _block(height: float = 10.0) -> list[Feature]:
    sketch = feature("f1", "testSketch", rects=[rect("l1", 0, 0, 30, 20)])
    return [sketch, _extrude("f2", extent={"type": "distance", "forward": height})]


def test_fillet_and_chamfer_volumes(session: Session, job: JobContext) -> None:
    fillet = feature("f3", "fillet", targetBody="f2", edges=_top_edges(), size=2.0)
    result = _run(session, job, document(*_block(), fillet))
    assert _volume(result, "f2") == pytest.approx(5917.227, abs=EXACT)
    chamfer = feature("f3", "fillet", targetBody="f2", edges=_top_edges(), size=1.5, mode="chamfer")
    assert _volume(_run(session, job, document(*_block(), chamfer)), "f2") == pytest.approx(
        5892.0, abs=EXACT
    )


def test_too_large_fillet_fails(session: Session, job: JobContext) -> None:
    fillet = feature("f3", "fillet", targetBody="f2", edges=_top_edges(), size=12.0)
    result = _run(session, job, document(*_block(), fillet))
    code, params = _error(result, "f3")
    assert code == "cad.filletFailed"
    assert params["size"] == 12.0
    # The body keeps its state before the failed feature.
    assert _volume(result, "f2") == pytest.approx(6000.0, abs=EXACT)


def test_fillet_survives_a_new_extrusion_height(session: Session, job: JobContext) -> None:
    fillet = feature("f3", "fillet", targetBody="f2", edges=_top_edges(), size=2.0)
    first = _run(session, job, document(*_block(10.0), fillet))
    assert _volume(first, "f2") == pytest.approx(5917.227, abs=EXACT)
    taller = _run(session, job, document(*_block(15.0), fillet))
    assert taller.statuses["f3"].state == "ok"
    assert _volume(taller, "f2") == pytest.approx(5917.227 + 30 * 20 * 5, abs=EXACT)


def test_fillet_after_a_splitting_cut_picks_the_edge_by_point(
    session: Session, job: JobContext
) -> None:
    slot = feature("f3", "testSketch", rects=[rect("s", 12, -1, 6, 22)])
    # A slot across the bottom (z = 0..5) splits the bottom cap in two.
    cut = _extrude(
        "f4",
        sketch="f3",
        extent={"type": "distance", "forward": 10.0},
        direction="symmetric",
        operation="cut",
        target_body="f2",
    )
    edge = {"faces": ["f2:cap:start", "f2:side:l1e0"], "point": [28.0, 0.0, 0.0]}
    fillet = feature("f5", "fillet", targetBody="f2", edges=[edge], size=1.0)
    result = _run(session, job, document(*_block(), slot, cut, fillet))
    assert result.statuses["f5"].state == "ok"
    rounded = 6000 - 600 - 12 * (1 - math.pi / 4)
    assert _volume(result, "f2") == pytest.approx(rounded, abs=EXACT)
    missing = {"faces": ["f2:cap:start", "f9:side:x"], "point": [0.0, 0.0, 0.0]}
    broken = feature("f5", "fillet", targetBody="f2", edges=[edge, missing], size=1.0)
    failed = _run(session, job, document(*_block(), slot, cut, broken))
    assert _error(failed, "f5") == ("cad.edgeNotFound", {"index": 1})


# --- History and timing ------------------------------------------------------------------------


def _long_history(height: float) -> Document:
    features: list[Feature] = [*_block(height)]
    next_id = 3
    for column in range(9):
        hole_sketch = feature(
            f"f{next_id}", "testSketch", rects=[rect("h", 2 + 3 * column, 8, 1.5, 1.5)]
        )
        hole = _extrude(
            f"f{next_id + 1}",
            sketch=f"f{next_id}",
            extent={"type": "distance", "forward": 30.0, "backward": 5.0},
            operation="cut",
            target_body="f2",
        )
        features += [hole_sketch, hole]
        next_id += 2
    return replace(document(*features), next_id=next_id)


def test_twenty_feature_history_rebuilds_within_a_second(session: Session, job: JobContext) -> None:
    import time

    env = session.environment()
    base = _long_history(10.0)
    assert len(base.features) == 20
    first = rebuild(base, env, job)
    assert all(status.state == "ok" for status in first.statuses.values())
    started = time.perf_counter()
    changed = rebuild(_long_history(12.0), env, job)
    elapsed = time.perf_counter() - started
    assert all(status.state == "ok" for status in changed.statuses.values())
    assert _volume(changed, "f2") == pytest.approx(30 * 20 * 12 - 9 * 1.5 * 1.5 * 12, abs=EXACT)
    assert elapsed < budget(1.0)
