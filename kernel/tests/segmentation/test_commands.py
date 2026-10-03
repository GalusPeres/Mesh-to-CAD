"""The regions protocol commands against a session holding the noisy test block."""

from __future__ import annotations

import time

import numpy as np
import pytest

from m2c_kernel.commands.regions import (
    CreateParams,
    DeleteParams,
    GrowParams,
    MergeParams,
    RegionRename,
    SegmentParams,
    UpdateParams,
    regions_create,
    regions_delete,
    regions_grow,
    regions_merge,
    regions_segment,
    regions_update,
)
from m2c_kernel.document.model import Region, Scan
from m2c_kernel.mesh.topology import FaceGraph, edge_topology
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.segmentation.api import adjacency
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.segmentation.conftest import NoisyPart, open_block_document

pytestmark = pytest.mark.occt


def _faces(mask: np.ndarray) -> np.ndarray:
    return np.nonzero(mask)[0].astype(np.uint32)


def _labels(session: Session) -> np.ndarray:
    ref = session.document.regions.labels
    assert ref is not None
    return session.blobs.get(ref)


def _region(session: Session, region_id: str) -> Region:
    return next(item for item in session.document.regions.items if item.id == region_id)


def _assert_consistent(session: Session, block: NoisyPart) -> None:
    """Face counts match the labels, and touching regions have different colours."""
    labels = _labels(session)
    items = session.document.regions.items
    counts = np.bincount(labels, minlength=max(item.label for item in items) + 1)
    for item in items:
        assert item.face_count == counts[item.label] > 0
    assert set(np.unique(labels[labels > 0]).tolist()) == {item.label for item in items}
    colors = {item.label: item.color_index for item in items}
    pairs = FaceGraph(edge_topology(block.mesh.faces)).pairs
    for a, b in adjacency(labels, pairs):
        assert colors[a] != colors[b]


@pytest.fixture
def scan(session: Session, job: JobContext, small_block: NoisyPart) -> Scan:
    return open_block_document(session, small_block, job)


def test_creating_a_region_classifies_it_and_takes_its_faces_from_others(
    session: Session, job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    top = small_block.truth(small_block.plane_face((0.0, 0.0, 1.0), 20.0))
    first = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(top)))
    region = _region(session, first.region_id or "")
    assert region.kind == "plane"
    assert region.rms is not None and region.rms < 0.05
    assert region.name is None
    assert region.face_count == int(top.sum())

    # a second region over half of the top plane and the hole
    hole = small_block.truth(small_block.cylinder_faces(8.0)[0])
    left = top & (small_block.mesh.face_centroids[:, 0] < 40.0)
    second = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(left | hole)))
    labels = _labels(session)
    assert np.all(labels[left | hole] == _region(session, second.region_id or "").label)
    assert _region(session, first.region_id or "").face_count == int((top & ~left).sum())
    assert _region(session, second.region_id or "").kind == "unknown"
    _assert_consistent(session, small_block)
    assert session.document.next_id == 3


def test_updating_adds_removes_and_renames(
    session: Session, job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    (hole,) = small_block.cylinder_faces(8.0)
    truth = small_block.truth(hole)
    upper = truth & (small_block.mesh.face_centroids[:, 2] > 10.0)
    created = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(upper)))
    region_id = created.region_id or ""
    regions_update(
        job, UpdateParams(region_id=region_id, scan_key=scan.key, add_faces=_faces(truth))
    )
    assert _region(session, region_id).face_count == int(truth.sum())
    assert _region(session, region_id).kind == "cylinder"

    regions_update(
        job, UpdateParams(region_id=region_id, scan_key=scan.key, remove_faces=_faces(upper))
    )
    assert _region(session, region_id).face_count == int((truth & ~upper).sum())

    regions_update(
        job, UpdateParams(region_id=region_id, scan_key=scan.key, rename=RegionRename("Bohrung"))
    )
    assert _region(session, region_id).name == "Bohrung"
    regions_update(
        job, UpdateParams(region_id=region_id, scan_key=scan.key, rename=RegionRename("  "))
    )
    assert _region(session, region_id).name is None

    result = regions_update(
        job, UpdateParams(region_id=region_id, scan_key=scan.key, remove_faces=_faces(truth))
    )
    assert result.region_id is None
    assert session.document.regions.items == ()
    assert session.document.regions.labels is None


def test_merging_keeps_the_largest_region_and_refits_the_type(
    session: Session, job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    (hole,) = small_block.cylinder_faces(8.0)
    truth = small_block.truth(hole)
    lower = truth & (small_block.mesh.face_centroids[:, 2] < 6.0)
    small = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(lower)))
    large = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(truth & ~lower)))
    regions_update(
        job,
        UpdateParams(region_id=large.region_id or "", scan_key=scan.key, rename=RegionRename("A")),
    )
    color = _region(session, large.region_id or "").color_index
    merged = regions_merge(
        job, MergeParams(region_ids=[small.region_id or "", large.region_id or ""])
    )
    assert merged.region_id == large.region_id
    (region,) = session.document.regions.items
    assert region.name == "A"
    assert region.color_index == color
    assert region.face_count == int(truth.sum())
    assert region.kind == "cylinder"


def test_deleting_leaves_the_faces_unassigned(
    session: Session, job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    sphere = small_block.truth(small_block.face_of("sphere"))
    top = small_block.truth(small_block.plane_face((0.0, 0.0, 1.0), 20.0))
    kept = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(top)))
    gone = regions_create(job, CreateParams(scan_key=scan.key, faces=_faces(sphere)))
    regions_delete(job, DeleteParams(region_ids=[gone.region_id or ""]))
    labels = _labels(session)
    assert not labels[sphere].any()
    assert [item.id for item in session.document.regions.items] == [kept.region_id]


def test_invalid_requests_fail_with_their_codes(
    job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    faces = _faces(small_block.truth(small_block.face_of("sphere")))
    cases = [
        (lambda: regions_create(job, CreateParams(scan_key="scan:old", faces=faces)), "staleScan"),
        (
            lambda: regions_create(
                job, CreateParams(scan_key=scan.key, faces=np.zeros(0, np.uint32))
            ),
            "emptySelection",
        ),
        (
            lambda: regions_create(
                job, CreateParams(scan_key=scan.key, faces=np.array([10**8], np.uint32))
            ),
            "invalidFace",
        ),
        (lambda: regions_merge(job, MergeParams(region_ids=["r1", "r1"])), "mergeNeedsTwo"),
        (lambda: regions_delete(job, DeleteParams(region_ids=["r99"])), "unknownRegion"),
        (
            lambda: regions_grow(job, GrowParams(scan_key=scan.key, seed_face=-1)),
            "invalidFace",
        ),
    ]
    for call, code in cases:
        with pytest.raises(KernelError) as caught:
            call()
        assert caught.value.code == f"regions.{code}"


def test_grow_returns_the_surface_under_the_seed(
    job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    (hole,) = small_block.cylinder_faces(8.0)
    seed = small_block.interior_face(hole)
    result = regions_grow(job, GrowParams(scan_key=scan.key, seed_face=seed))
    assert result.kind == "cylinder"
    assert result.faces.dtype == np.uint32
    assert small_block.iou(result.faces.astype(np.int64), hole) >= 0.95
    assert 0.08 < result.tolerance < 0.2  # 4 x the scan noise of 0.03 mm


def test_segmentation_preview_commit_and_repeat(
    session: Session, job: JobContext, scan: Scan, small_block: NoisyPart
) -> None:
    revision = session.document.revision
    preview = regions_segment(job, SegmentParams(scan_key=scan.key, dry_run=True))
    assert session.document.revision == revision
    assert preview.labels is not None and preview.color_index is not None
    assert 14 <= len(preview.regions) <= 18
    assert sum(region.face_count for region in preview.regions) == int((preview.labels > 0).sum())

    start = time.perf_counter()
    committed = regions_segment(job, SegmentParams(scan_key=scan.key, dry_run=False))
    assert time.perf_counter() - start < 2.0  # the preview is reused
    assert committed.revision == session.document.revision
    assert np.array_equal(_labels(session), preview.labels)
    items = session.document.regions.items
    assert len(items) == len(preview.regions)
    assert all(item.name is None for item in items)
    assert [preview.color_index[item.label] for item in items] == [
        item.color_index for item in items
    ]
    _assert_consistent(session, small_block)

    # segmenting again with the same settings keeps ids and colours of the regions
    renamed = items[0]
    regions_update(
        job, UpdateParams(region_id=renamed.id, scan_key=scan.key, rename=RegionRename("Boden"))
    )
    regions_segment(job, SegmentParams(scan_key=scan.key, dry_run=False))
    again = {item.id: item for item in session.document.regions.items}
    assert again[renamed.id].name == "Boden"
    before = {item.id: item.color_index for item in items}
    kept = [region_id for region_id in before if region_id in again]
    assert len(kept) >= len(items) - 2
    assert all(again[region_id].color_index == before[region_id] for region_id in kept)
