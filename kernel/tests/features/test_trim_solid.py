"""Trim to a solid: a net band, planes and bodies cut each other into pieces."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from m2c_kernel.cad.tessellate import tessellate
from m2c_kernel.document.model import Document, Feature
from m2c_kernel.document.rebuild import RebuildResult, rebuild
from m2c_kernel.export.api import check_body
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.features.helpers import document, feature, rect, scan_of, upstream_test_types
from tests.synthetic.nets import BandNet, band_net

pytestmark = pytest.mark.occt


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    with upstream_test_types():
        yield


def _run(session: Session, job: JobContext, doc: Document) -> RebuildResult:
    return rebuild(doc, session.environment(), job)


def _net(session: Session, net: BandNet, feature_id: str = "n1") -> Feature:
    return feature(
        feature_id,
        "freeformNet",
        vertices=session.blobs.put(net.vertices.astype(np.float64)),
        quads=session.blobs.put(net.quads.astype(np.uint32)),
        faces=None,
    )


def _plane(feature_id: str, height: float) -> Feature:
    return feature(feature_id, "testConstruction", kind="plane", origin=(0, 0, height))


def _trim(feature_id: str = "t1", **params: Any) -> Feature:
    params = {"bodies": [], "surfaces": [], "planes": [], "pieces": [], **params}
    return feature(feature_id, "trimSolid", **params)


def _cube_scan(session: Session) -> Any:
    """A closed scan far from the inputs: the scan is required, not used by these cases."""
    vertices = np.array(
        [[x, y, z] for x in (100, 101) for y in (0, 1) for z in (0, 1)], dtype=np.float64
    )
    faces = np.array(
        [
            *([0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4]),
            *([2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]),
        ]
    )
    return scan_of(session, vertices, faces)


def test_a_band_pushed_past_two_planes_becomes_one_solid(session: Session, job: JobContext) -> None:
    doc = document(
        _net(session, band_net()),
        _plane("p1", 0.0),
        _plane("p2", 10.0),
        _trim(surfaces=["n1"], planes=["p1", "p2"]),
        scan=_cube_scan(session),
    )
    result = _run(session, job, doc)
    assert result.statuses["t1"].state == "ok", result.statuses["t1"].error
    body = result.bodies["t1"]
    check = check_body(body)
    assert not check.blocking and check.closed and check.solids == 1
    # The wall's limit surface lies inside its control ellipses (semi-axes 20 x 12 at
    # the bottom, 16 x 9.6 at the top): between the inner and outer elliptic frustum.
    volume = result.body_checks["t1"].volume
    outer = np.pi / 3 * 10 * (20 * 12 + 16 * 9.6 + np.sqrt(20 * 12 * 16 * 9.6))
    assert 0.85 * outer < volume < outer
    assert {"p1:cap", "p2:cap", "n1:face"} <= set(body.face_tags)
    assert result.statuses["t1"].stats["pieces"] == 1.0


def test_a_band_that_stops_short_of_a_plane_encloses_nothing(
    session: Session, job: JobContext
) -> None:
    doc = document(
        _net(session, band_net(top=8.0)),
        _plane("p1", 0.0),
        _plane("p2", 10.0),
        _trim(surfaces=["n1"], planes=["p1", "p2"]),
        scan=_cube_scan(session),
    )
    status = _run(session, job, doc).statuses["t1"]
    assert status.state == "error" and status.error is not None
    assert status.error.code == "cad.noClosedRegion"


def _box_and_band(session: Session, scan: Any, pieces: list[dict[str, Any]]) -> Document:
    return document(
        feature("s1", "testSketch", rects=[rect("l1", -30, -20, 60, 40)]),
        feature("b1", "extrude", sketch="s1", extent={"type": "distance", "forward": 10.0}),
        _net(session, band_net()),
        _trim(bodies=["b1"], surfaces=["n1"], pieces=pieces),
        scan=scan,
    )


def test_pieces_inside_the_scan_are_kept_and_clicks_change_that(
    session: Session, job: JobContext
) -> None:
    # The scan is the part the band encloses between z = 0 and 10 (closed).
    inner = _run(
        session,
        job,
        document(
            _net(session, band_net()),
            _plane("p1", 0.0),
            _plane("p2", 10.0),
            _trim(surfaces=["n1"], planes=["p1", "p2"]),
            scan=_cube_scan(session),
        ),
    )
    inner_volume = inner.body_checks["t1"].volume
    mesh = tessellate(inner.bodies["t1"].shape, linear_deflection=0.05)
    scan = scan_of(session, mesh.vertices, mesh.triangles)

    auto = _run(session, job, _box_and_band(session, scan, []))
    assert auto.statuses["t1"].stats == {"pieces": 2.0, "kept": 1.0}
    assert auto.body_checks["b1"].volume == pytest.approx(inner_volume, rel=1e-6)
    assert auto.body_owner["b1"] == "t1"
    assert len(auto.outputs["t1"].display) == 1  # the removed outer piece, as a ghost

    # A click on the box's corner keeps the outer piece as well: the whole box again.
    corner = {"point": [30.0, 20.0, 10.0], "keep": True}
    both = _run(session, job, _box_and_band(session, scan, [corner]))
    assert both.body_checks["b1"].volume == pytest.approx(60 * 40 * 10, rel=1e-6)
    assert both.statuses["t1"].stats["kept"] == 2.0

    # Removing the inner piece too keeps only the outer ring; removing all is an error.
    centre = {"point": [0.0, 0.0, 10.0], "keep": False}
    ring = _run(session, job, _box_and_band(session, scan, [corner, centre]))
    assert ring.body_checks["b1"].volume == pytest.approx(24000 - inner_volume, rel=1e-4)
    gone = {"point": [30.0, 20.0, 10.0], "keep": False}
    empty = _run(session, job, _box_and_band(session, scan, [centre, gone]))
    assert empty.statuses["t1"].error is not None
    assert empty.statuses["t1"].error.code == "cad.noPieceKept"


def test_planes_alone_cannot_be_trimmed(session: Session, job: JobContext) -> None:
    doc = document(_plane("p1", 0.0), _trim(planes=["p1"]), scan=_cube_scan(session))
    status = _run(session, job, doc).statuses["t1"]
    assert status.error is not None and status.error.code == "cad.trimNeedsSurface"
