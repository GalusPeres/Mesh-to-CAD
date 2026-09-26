"""Rigid frames: the 3-2-1 construction, the PCA fallback and the user adjustments.

A transform `T` maps scan coordinates to part coordinates, `p_part = R (p_scan - o)`:
the rows of `R` are the part axes in scan coordinates and `o` is the part origin in
scan coordinates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.alignment import ErrorCode
from m2c_kernel.document.model import AlignmentAdjust
from m2c_kernel.geometry import FloatArray, frame_from_axis, unit

PARALLEL_SIN = float(np.sin(np.radians(5.0)))
"""Directions closer than 5 degrees count as parallel; constraints closer than that as dependent."""
DISTINCT_AXES_MM = 1.0
"""Two parallel axes further apart than this define a direction (bolt holes of a flange)."""

type DatumKind = Literal["plane", "axis", "point"]
type IntArray = npt.NDArray[np.int64]


class FrameError(ValueError):
    """The inputs do not define a frame; `code` is an `alignment.*` error code."""

    def __init__(self, code: ErrorCode, role: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.role = role


@dataclass(frozen=True)
class Datum:
    """A plane, an axis or a point in scan coordinates.

    `direction` is the plane normal pointing into the material, or the axis direction;
    it is unused for points.
    """

    kind: DatumKind
    point: FloatArray
    direction: FloatArray
    role: str = ""


class Surface:
    """Area-weighted moments of the scan surface, computed on first use."""

    def __init__(self, vertices: FloatArray, faces: IntArray) -> None:
        self.vertices = vertices
        self.faces = faces

    @cached_property
    def moments(self) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        """Centroid, second-moment matrix, face areas and centred face centroids.

        The second moment of a triangle about the centroid is exact:
        `A / 12 (a a^T + b b^T + c c^T + s s^T)` with `s = a + b + c`.
        """
        corners = self.vertices[self.faces]
        a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
        area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        total = max(float(area.sum()), 1e-300)
        centroid = (area[:, None] * (a + b + c) / 3.0).sum(axis=0) / total
        a, b, c = a - centroid, b - centroid, c - centroid
        s = a + b + c
        second = sum(np.einsum("i,ij,ik->jk", area, v, v) for v in (a, b, c, s)) / 12.0
        return centroid, second / total, area, s / 3.0

    def skew_sign(self, direction: FloatArray) -> float:
        """+1 when the area-weighted third moment along `direction` is positive, else -1.

        Gives symmetric-looking axes a sign that depends only on the shape, so the same
        part ends up in the same pose from any scan pose.
        """
        _, _, area, centred = self.moments
        return 1.0 if float((area * (centred @ direction) ** 3).sum()) >= 0.0 else -1.0

    def principal_rows(self) -> FloatArray:
        """Principal axes (largest extent first) with skew-rule signs, as frame rows."""
        _, second, _, _ = self.moments
        _, vectors = np.linalg.eigh(second)
        rows = vectors[:, ::-1].T.copy()
        for index in range(2):
            rows[index] *= self.skew_sign(rows[index])
        rows[2] = np.cross(rows[0], rows[1])
        return rows

    def in_plane_direction(self, z: FloatArray) -> FloatArray:
        """The principal direction of the surface perpendicular to `z`, skew-rule sign."""
        _, second, _, _ = self.moments
        e1, e2 = frame_from_axis(z)
        basis = np.stack([e1, e2])
        _, vectors = np.linalg.eigh(basis @ second @ basis.T)
        direction = unit(vectors[:, -1] @ basis)
        return direction * self.skew_sign(direction)

    def minimum_along(self, direction: FloatArray) -> float:
        return float((self.vertices @ direction).min())


def make_transform(rows: FloatArray, origin: FloatArray) -> FloatArray:
    transform = np.eye(4)
    transform[:3, :3] = rows
    transform[:3, 3] = -rows @ origin
    return transform


def apply(transform: FloatArray, points: FloatArray) -> FloatArray:
    result: FloatArray = points @ transform[:3, :3].T + transform[:3, 3]
    return result


def build_frame(
    datums: Sequence[Datum], surface: Surface, require_point: bool
) -> tuple[FloatArray, FloatArray]:
    """Rows of the part axes and the origin (scan coordinates) of a 3-2-1 frame.

    The secondary datum must add a direction or a position; with `require_point`
    (a tertiary datum was given) the datums together must fix a point.
    """
    rows, direction_from = frame_rows(datums, surface)
    origin, added = frame_origin(rows, datums, surface)
    if len(datums) > 1 and direction_from != 1 and added[1] == 0:
        raise FrameError(ErrorCode.PARALLEL_INPUTS, datums[1].role)
    if require_point and sum(added) < 3:
        raise FrameError(ErrorCode.NO_POINT, datums[-1].role)
    return rows, origin


def frame_rows(datums: Sequence[Datum], surface: Surface) -> tuple[FloatArray, int | None]:
    """Part axes as rows, and the index of the datum that fixed the in-plane direction.

    Z comes from the primary datum. A plane across Z gives Y (the XZ plane is that
    plane), an axis across Z gives X. A plane perpendicular to a primary axis (the end
    face of a shaft) only chooses the sign of Z; two distinct axes parallel to Z give X
    along the line joining them. Without any of these the in-plane direction is the
    principal direction of the scan.
    """
    primary = datums[0]
    if primary.kind == "point":
        raise FrameError(ErrorCode.UNSUPPORTED_INPUT, primary.role)
    z = unit(primary.direction)
    parallel_axis = primary.point if primary.kind == "axis" else None
    for index, datum in enumerate(datums[1:], start=1):
        if datum.kind == "point":
            continue
        along = float(datum.direction @ z)
        across = datum.direction - along * z
        if np.linalg.norm(across) >= PARALLEL_SIN:
            if datum.kind == "plane":
                y = unit(across)
                return np.stack([np.cross(y, z), y, z]), index
            x = unit(across)
            return np.stack([x, np.cross(z, x), z]), index
        if primary.kind == "axis" and datum.kind == "plane":
            z = z if along > 0 else -z
        elif datum.kind == "axis":
            if parallel_axis is not None:
                joining = datum.point - parallel_axis
                joining = joining - float(joining @ z) * z
                if np.linalg.norm(joining) > DISTINCT_AXES_MM:
                    x = unit(joining)
                    return np.stack([x, np.cross(z, x), z]), index
            parallel_axis = datum.point
    x = surface.in_plane_direction(z)
    return np.stack([x, np.cross(z, x), z]), None


def _constraints(datum: Datum, rows: FloatArray) -> list[FloatArray]:
    """Directions whose coordinate the datum fixes (plane: 1, axis: 2, point: 3)."""
    if datum.kind == "plane":
        return [unit(datum.direction)]
    if datum.kind == "axis":
        e1, e2 = frame_from_axis(datum.direction)
        return [e1, e2]
    return [row.copy() for row in rows]


def frame_origin(
    rows: FloatArray, datums: Sequence[Datum], surface: Surface
) -> tuple[FloatArray, list[int]]:
    """The origin fixed by the datums (scan coordinates) and the constraints each added.

    Constraints are taken in datum order and only while they are independent of the
    earlier ones, so the primary datum always holds exactly. Directions that no datum
    fixes go to the bounding-box minimum.
    """
    accepted: list[FloatArray] = []
    values: list[float] = []
    added: list[int] = []
    for datum in datums:
        count = 0
        for normal in _constraints(datum, rows):
            residual = normal.copy()
            for basis in _orthonormal(accepted):
                residual = residual - float(residual @ basis) * basis
            if np.linalg.norm(residual) < PARALLEL_SIN:
                continue
            accepted.append(normal)
            values.append(float(normal @ datum.point))
            count += 1
        added.append(count)
    point = np.zeros(3)
    if accepted:
        point = np.linalg.lstsq(np.asarray(accepted), np.asarray(values), rcond=None)[0]
    for free in _free_directions(accepted, rows):
        point = point + (surface.minimum_along(free) - float(point @ free)) * free
    return point, added


def _orthonormal(vectors: Sequence[FloatArray]) -> list[FloatArray]:
    basis: list[FloatArray] = []
    for vector in vectors:
        residual = vector.copy()
        for item in basis:
            residual = residual - float(residual @ item) * item
        length = float(np.linalg.norm(residual))
        if length > 1e-12:
            basis.append(residual / length)
    return basis


def _free_directions(constraints: Sequence[FloatArray], rows: FloatArray) -> list[FloatArray]:
    """Orthonormal directions the constraints leave free, aligned with the frame axes."""
    basis = _orthonormal(constraints)
    free: list[FloatArray] = []
    for row in rows:
        residual = row.copy()
        for item in (*basis, *free):
            residual = residual - float(residual @ item) * item
        length = float(np.linalg.norm(residual))
        if length > PARALLEL_SIN:
            free.append(residual / length)
    return free


def adjustment_rotation(adjust: AlignmentAdjust) -> FloatArray:
    """Rotation applied in part coordinates.

    `flip_z` turns the part over (180 degrees about X), `flip_x` reverses X and Y
    (180 degrees about Z), `rotate_z90` adds quarter turns about Z.
    """
    rotation = np.eye(3)
    if adjust.flip_z:
        rotation = np.diag([1.0, -1.0, -1.0]) @ rotation
    if adjust.flip_x:
        rotation = np.diag([-1.0, -1.0, 1.0]) @ rotation
    quarter = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    for _ in range(adjust.rotate_z90 % 4):
        rotation = quarter @ rotation
    return rotation


def line_angle_deg(a: FloatArray, b: FloatArray) -> float:
    """Angle between two lines (direction sign ignored), 0 to 90 degrees."""
    cosine = abs(float(unit(a) @ unit(b)))
    return float(np.degrees(np.arccos(min(cosine, 1.0))))
