"""Recognise a part: its base planes and the features on them, as a designer reads it.

`recognize` finds the large flat faces (`planes.py`), the raised and sunk features on
each (`relief.py`), restores design intent per face (`intent.py`) and merges what was
seen from two faces: a through hole appears on both sides of a plate, a bore in a
hub on the hub's top and on the flange it stands on. Of such a pair the deeper
reading is kept (it spans the whole feature).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.intent import beautify
from m2c_kernel.recognition.outline import Outline, outline_points
from m2c_kernel.recognition.planes import BasePlane, base_planes
from m2c_kernel.recognition.relief import (
    Relief,
    find_reliefs,
    inside_contour,
    mesh_data,
    signed_area,
)

type IntArray = npt.NDArray[np.int64]

PLANE_SHARE = 0.01
"""Smallest base plane, as a share of the part's area (a hub's top on a flange)."""
MAX_DESIGN_NOISE_MM = 0.05
"""The design noise is at most this: more would hide shallow designed features."""
SAME_AXIS = 0.99
SAME_PLACE_MM = 0.6
SAME_SIZE = 0.1
SAME_AREA = 2.0
"""Contours of different shapes are the same feature within this area ratio."""


@dataclass(frozen=True)
class Feature:
    """A recognised feature on one of the part's base planes."""

    plane: int
    relief: Relief

    @property
    def outline(self) -> Outline:
        """The fitted outline in the plane's (u, v) frame."""
        return self.relief.outline


@dataclass(frozen=True)
class Recognition:
    """The base planes of a part and the features on them (no duplicates)."""

    planes: tuple[BasePlane, ...]
    features: tuple[Feature, ...]

    def outline_3d(self, feature: Feature, at: float) -> FloatArray:
        """The fitted outline of a feature in part coordinates, `at` mm above its plane."""
        points = outline_points(feature.outline)
        if len(points) == 0:
            points = feature.relief.contour
        plane = self.planes[feature.plane]
        uvh = np.column_stack([points, np.full(len(points), at)])
        return plane.from_plane(uvh)


def recognize(
    vertices: FloatArray,
    faces: IntArray,
    noise: float,
    check_cancelled: Callable[[], None] = lambda: None,
) -> Recognition:
    """Base planes and their features, with design intent, without duplicates."""
    planes = base_planes(vertices, faces, noise, min_share=PLANE_SHARE)
    data = mesh_data(vertices, faces)
    tolerance = design_noise(planes, noise)
    features: list[Feature] = []
    for index, plane in enumerate(planes):
        check_cancelled()
        reliefs = beautify(find_reliefs(data, plane, tolerance))
        offset = len(features)
        for relief in reliefs:
            parent = None if relief.parent is None else relief.parent + offset
            features.append(Feature(index, _with_parent(relief, parent)))
    return Recognition(tuple(planes), tuple(_without_duplicates(planes, features)))


def design_noise(planes: Sequence[BasePlane], noise: float) -> float:
    """How closely the scan follows a designed face: the largest plane's RMS.

    Scanner software smooths its meshes, so their roughness (the measured noise) can
    be far below how much a moulded or printed face deviates from the plane it was
    designed as; outlines and flat tops are judged against that deviation. At least
    the measured noise, at most `MAX_DESIGN_NOISE_MM`.
    """
    if not planes:
        return noise
    largest = max(planes, key=lambda plane: plane.area)
    return float(max(noise, min(largest.rms, MAX_DESIGN_NOISE_MM)))


def _with_parent(relief: Relief, parent: int | None) -> Relief:
    return replace(relief, parent=parent, children=[])


def _axis_point(planes: list[BasePlane], feature: Feature) -> tuple[FloatArray, FloatArray]:
    plane = planes[feature.plane]
    cx, cy = feature.outline.center
    point = plane.from_plane(np.array([[cx, cy, feature.relief.level]]))[0]
    return point, plane.normal


def _size(outline: Outline) -> float:
    values = outline.named()
    for name in ("radius", "length", "width", "outer"):
        if name in values:
            return float(values[name])
    return 0.0


def _same(planes: list[BasePlane], a: Feature, b: Feature) -> bool:
    if a.plane == b.plane or a.relief.kind != b.relief.kind:
        return False
    point_a, axis_a = _axis_point(planes, a)
    point_b, axis_b = _axis_point(planes, b)
    if abs(float(axis_a @ axis_b)) < SAME_AXIS:
        return False
    if a.outline.kind != b.outline.kind:
        # Explained by different shapes (one a free profile): compare the contours.
        return _overlap(planes, a, b)
    offset = point_b - point_a
    lateral = offset - (offset @ axis_a) * axis_a
    size_a, size_b = _size(a.outline), _size(b.outline)
    if float(np.linalg.norm(lateral)) > max(SAME_PLACE_MM, 0.05 * max(size_a, size_b)):
        return False
    return abs(size_a - size_b) <= SAME_SIZE * max(size_a, size_b, 1e-9)


def _overlap(planes: list[BasePlane], a: Feature, b: Feature) -> bool:
    """Whether the measured contours, seen along a's axis, cover about the same area."""
    plane_a, plane_b = planes[a.plane], planes[b.plane]
    contour_b = b.relief.contour
    at = np.full(len(contour_b), b.relief.level)
    seen = plane_a.to_plane(plane_b.from_plane(np.column_stack([contour_b, at])))[:, :2]
    contour_a = a.relief.contour
    area_a, area_b = abs(signed_area(contour_a)), abs(signed_area(seen))
    if not 1.0 / SAME_AREA < area_b / max(area_a, 1e-9) < SAME_AREA:
        return False
    centre_a, centre_b = contour_a.mean(axis=0), seen.mean(axis=0)
    return bool(
        inside_contour(centre_b[None], contour_a)[0] and inside_contour(centre_a[None], seen)[0]
    )


def _preferred(a: Feature, b: Feature) -> bool:
    """Whether a describes the feature better than b: a simple shape, else the deeper."""
    if (a.outline.kind == "profile") != (b.outline.kind == "profile"):
        return b.outline.kind == "profile"
    return a.relief.height >= b.relief.height


def _without_duplicates(planes: list[BasePlane], features: list[Feature]) -> list[Feature]:
    """One feature per real feature; parents and children re-indexed."""
    keep = [True] * len(features)
    for i, a in enumerate(features):
        if not keep[i]:
            continue
        for j in range(i + 1, len(features)):
            if keep[j] and _same(planes, a, features[j]):
                better = i if _preferred(a, features[j]) else j
                keep[i if better == j else j] = False
                if better == j:
                    break
    # A feature whose parent was dropped stands on the base plane again.
    new_index: dict[int, int] = {}
    kept: list[Feature] = []
    for i, feature in enumerate(features):
        if keep[i]:
            new_index[i] = len(kept)
            kept.append(feature)
    result: list[Feature] = []
    for feature in kept:
        parent = feature.relief.parent
        mapped = new_index.get(parent) if parent is not None else None
        result.append(Feature(feature.plane, _with_parent(feature.relief, mapped)))
    for index, feature in enumerate(result):
        if feature.relief.parent is not None:
            result[feature.relief.parent].relief.children.append(index)
    return result
