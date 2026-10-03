"""Scan queries of automation clients against a session holding the noisy test block."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.commands.automation import (
    BoundsParams,
    FacesInBoxParams,
    bounds,
    faces_in_box,
)
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.segmentation.conftest import NoisyPart, open_block_document

pytestmark = pytest.mark.occt


def test_bounds_and_facing_faces_select_the_top_of_the_block(
    session: Session, job: JobContext, small_block: NoisyPart
) -> None:
    open_block_document(session, small_block, job)
    box = bounds(job, BoundsParams())
    low, high = np.asarray(box.min), np.asarray(box.max)
    assert box.faces == len(small_block.mesh.faces)

    # Everything in the box, then only the triangles facing up.
    everything = faces_in_box(job, FacesInBoxParams(min=box.min, max=box.max))
    assert everything.count == box.faces
    top = faces_in_box(
        job, FacesInBoxParams(min=box.min, max=box.max, facing=(0.0, 0.0, 1.0), max_angle_deg=20)
    )
    normals = small_block.mesh.face_normals[top.faces.astype(np.int64)]
    assert 0 < top.count < box.faces
    assert np.all(normals[:, 2] > np.cos(np.radians(20)))

    # A thin slab below the top only holds side triangles, and none of them face up.
    slab = faces_in_box(
        job,
        FacesInBoxParams(
            min=(low[0], low[1], high[2] - 2.0),
            max=(high[0], high[1], high[2] - 1.0),
            facing=(0.0, 0.0, 1.0),
        ),
    )
    assert slab.count == 0


def test_queries_need_a_scan(job: JobContext) -> None:
    with pytest.raises(KernelError):
        bounds(job, BoundsParams())
