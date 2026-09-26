"""3-2-1 frame construction from exact datums (no fitting involved)."""

from __future__ import annotations

import numpy as np
import pytest

from m2c_kernel.alignment.frames import (
    Datum,
    FrameError,
    Surface,
    adjustment_rotation,
    apply,
    build_frame,
    make_transform,
)
from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.document.model import AlignmentAdjust
from tests.synthetic import box_scan, random_rotation

X, Y, Z = np.eye(3)


def _plane(point: tuple[float, float, float], into: np.ndarray, role: str = "") -> Datum:
    return Datum("plane", np.asarray(point, dtype=np.float64), np.asarray(into), role)


def _axis(point: tuple[float, float, float], direction: np.ndarray, role: str = "") -> Datum:
    return Datum("axis", np.asarray(point, dtype=np.float64), np.asarray(direction), role)


@pytest.fixture(scope="module")
def box_surface() -> Surface:
    vertices, faces = box_scan((100.0, 70.0, 20.0), max_edge=10.0)
    return Surface(vertices, faces)


def _posed(datums: list[Datum], rotation: np.ndarray, offset: np.ndarray) -> list[Datum]:
    return [
        Datum(d.kind, rotation @ d.point + offset, rotation @ d.direction, d.role) for d in datums
    ]


def test_three_planes_give_the_design_frame(box_surface: Surface) -> None:
    rng = np.random.default_rng(3)
    rotation, offset = random_rotation(rng), rng.uniform(-100, 100, 3)
    design = [_plane((0, 0, 0), Z), _plane((0, 0, 0), Y), _plane((0, 0, 0), X)]
    posed_surface = Surface(box_surface.vertices @ rotation.T + offset, box_surface.faces)
    rows, origin = build_frame(_posed(design, rotation, offset), posed_surface, True)
    transform = make_transform(rows, origin)
    np.testing.assert_allclose(transform[:3, :3] @ rotation, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(apply(transform, offset[None])[0], 0.0, atol=1e-9)


def test_primary_holds_exactly_when_the_secondary_is_not_perpendicular(
    box_surface: Surface,
) -> None:
    tilted = np.array([0.0, np.cos(np.radians(80.0)), np.sin(np.radians(80.0))])
    rows, _ = build_frame([_plane((0, 0, 5), Z), _plane((0, 0, 0), tilted)], box_surface, False)
    np.testing.assert_allclose(rows[2], Z, atol=1e-12)
    np.testing.assert_allclose(rows[1], Y, atol=1e-12)


def test_free_coordinates_go_to_the_bounding_box_minimum(box_surface: Surface) -> None:
    shifted = Surface(box_surface.vertices + np.array([7.0, -3.0, 2.0]), box_surface.faces)
    rows, origin = build_frame([_plane((0, 0, 2), Z), _plane((0, -3, 0), Y)], shifted, False)
    np.testing.assert_allclose(origin, [7.0, -3.0, 2.0], atol=1e-9)
    np.testing.assert_allclose(rows, np.eye(3), atol=1e-12)


def test_axis_and_end_face(box_surface: Surface) -> None:
    rows, origin = build_frame(
        [_axis((5, 5, 40), -Z, "primary"), _plane((0, 0, 10), Z, "secondary")], box_surface, True
    )
    np.testing.assert_allclose(rows[2], Z, atol=1e-12)
    np.testing.assert_allclose(origin, [5, 5, 10], atol=1e-9)


def test_two_parallel_axes_give_x(box_surface: Surface) -> None:
    rows, origin = build_frame(
        [
            _plane((0, 0, 0), Z, "primary"),
            _axis((20, 30, 0), Z, "secondary"),
            _axis((20, 50, 0), -Z, "tertiary"),
        ],
        box_surface,
        True,
    )
    np.testing.assert_allclose(rows, [Y, -X, Z], atol=1e-12)
    np.testing.assert_allclose(origin, [20, 30, 0], atol=1e-9)


@pytest.mark.parametrize(
    ("datums", "code"),
    [
        ([_plane((0, 0, 0), Z), _plane((0, 0, 20), -Z, "secondary")], ErrorCode.PARALLEL_INPUTS),
        ([_axis((0, 0, 0), Z), _axis((0.1, 0, 5), Z, "secondary")], ErrorCode.PARALLEL_INPUTS),
        (
            [_plane((0, 0, 0), Z), _plane((0, 0, 0), Y), _plane((0, 9, 0), -Y, "tertiary")],
            ErrorCode.NO_POINT,
        ),
        (
            [_plane((0, 0, 0), Z), _axis((0, 0, 0), X), _plane((0, 0, 3), Z, "tertiary")],
            ErrorCode.NO_POINT,
        ),
        (
            [Datum("point", np.zeros(3), np.zeros(3), "primary"), _plane((0, 0, 0), Z)],
            ErrorCode.UNSUPPORTED_INPUT,
        ),
    ],
)
def test_invalid_datums(box_surface: Surface, datums: list[Datum], code: ErrorCode) -> None:
    with pytest.raises(FrameError) as raised:
        build_frame(datums, box_surface, require_point=len(datums) == 3)
    assert raised.value.code == code
    assert raised.value.role in ("primary", "secondary", "tertiary")


def test_adjustments_are_proper_rotations() -> None:
    for flip_x in (False, True):
        for flip_z in (False, True):
            for quarter in range(4):
                rotation = adjustment_rotation(AlignmentAdjust(flip_x, flip_z, quarter))
                np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-12)
                assert np.linalg.det(rotation) == pytest.approx(1.0)
    np.testing.assert_allclose(adjustment_rotation(AlignmentAdjust(flip_z=True)) @ Z, -Z)
    np.testing.assert_allclose(adjustment_rotation(AlignmentAdjust(flip_x=True)) @ X, -X)
    np.testing.assert_allclose(adjustment_rotation(AlignmentAdjust(rotate_z90=1)) @ X, Y)
