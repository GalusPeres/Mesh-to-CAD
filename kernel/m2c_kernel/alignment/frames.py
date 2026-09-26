"""Rigid frames: 3-2-1 construction, PCA fallback and the user adjustments.

A transform `T` maps scan coordinates to part coordinates, `p_part = R (p_scan - o)`:
the rows of `R` are the part axes in scan coordinates, `o` is the part origin in
scan coordinates. See `.work/research/algorithms-mesh.md` section 5.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from m2c_kernel.document.model import AlignmentAdjust
from m2c_kernel.geometry import FloatArray, unit

PARALLEL_SIN = float(np.sin(np.radians(5.0)))
"""Directions closer than 5 degrees count as parallel."""


class FrameError(ValueError):
    """The inputs do not define a frame; `code` is an `alignment.*` error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Datum:
    """A plane (`normal` points into the material) or an axis, in scan coordinates."""

    kind: str
    """'plane' or 'axis'."""
    point: FloatArray
    direction: FloatArray


def make_transform(rows: FloatArray, origin: FloatArray) -> FloatArray:
    transform = np.eye(4)
    transform[:3, :3] = rows
    transform[:3, 3] = -rows @ origin
    return transform


def apply(transform: FloatArray, points: FloatArray) -> FloatArray:
    result: FloatArray = points @ transform[:3, :3].T + transform[:3, 3]
    return result


def surface_moments(
    vertices: FloatArray, faces: np.ndarray
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Area-weighted centroid, covariance, face areas and centred face centroids."""
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = max(float(area.sum()), 1e-300)
    centroid = (area[:, None] * (a + b + c) / 3.0).sum(axis=0) / total
    a, b, c = a - centroid, b - centroid, c - centroid
    s = a + b + c
    moment = sum(np.einsum("i,ij,ik->jk", area, v, v) for v in (a, b, c, s)) / 12.0
    return centroid, moment / total, area, s / 3.0


def skew_sign(direction: FloatArray, area: FloatArray, centred: FloatArray) -> float:
    """+1 when the area-weighted third moment along `direction` is positive, else -1."""
    return 1.0 if float((area * (centred @ direction) ** 3).sum()) >= 0.0 else -1.0


def pca_rows(vertices: FloatArray, faces: np.ndarray) -> tuple[FloatArray, FloatArray]:
    """Principal axes (largest extent first) with deterministic signs, and the centroid."""
    centroid, moment, area, centred = surface_moments(vertices, faces)
    _, vectors = np.linalg.eigh(moment)
    rows = vectors[:, ::-1].T.copy()
    for index in range(2):
        rows[index] *= skew_sign(rows[index], area, centred)
    rows[2] = np.cross(rows[0], rows[1])
    return rows, centroid


def in_plane_direction(z: FloatArray, vertices: FloatArray, faces: np.ndarray) -> FloatArray:
    """The principal direction of the surface perpendicular to `z`, sign by the skew rule."""
    _, moment, area, centred = surface_moments(vertices, faces)
    e1 = unit(np.cross(z, [1.0, 0.0, 0.0] if abs(z[0]) < 0.9 else [0.0, 1.0, 0.0]))
    e2 = np.cross(z, e1)
    basis = np.stack([e1, e2])
    projected = basis @ moment @ basis.T
    _, vectors = np.linalg.eigh(projected)
    direction = unit(vectors[:, -1] @ basis)
    return direction * skew_sign(direction, area, centred)


def rows_from_datums(
    primary: Datum, others: list[Datum], vertices: FloatArray, faces: np.ndarray
) -> FloatArray:
    """Z from the primary datum, Y (plane) or X (axis) from the first non-parallel datum.

    An axis as primary with a perpendicular plane (a shaft and its end face) takes the
    sign of Z from that plane. Without a second direction the in-plane rotation follows
    the surface's principal direction.
    """
    z = unit(primary.direction)
    for datum in others:
        along = float(datum.direction @ z)
        if primary.kind == "axis" and datum.kind == "plane" and abs(along) > 1 - PARALLEL_SIN:
            z = z if along > 0 else -z
            continue
        projected = datum.direction - along * z
        if np.linalg.norm(projected) < PARALLEL_SIN:
            raise FrameError("alignment.parallelInputs")
        if datum.kind == "plane":
            y = unit(projected)
            return np.stack([np.cross(y, z), y, z])
        x = unit(projected)
        return np.stack([x, np.cross(z, x), z])
    x = in_plane_direction(z, vertices, faces)
    return np.stack([x, np.cross(z, x), z])


def origin_from_datums(
    rows: FloatArray, datums: list[Datum], vertices: FloatArray, require_point: bool
) -> FloatArray:
    """The point fixed by the datums; free directions go to the bounding-box minimum.

    A plane fixes one coordinate, an axis two. With `require_point` the datums must
    fix all three (three planes with independent normals, or an axis and a plane).
    """
    equations: list[FloatArray] = []
    values: list[float] = []
    for datum in datums:
        if datum.kind == "plane":
            normal = unit(datum.direction)
            equations.append(normal)
            values.append(float(normal @ datum.point))
        else:
            e1 = unit(
                np.cross(
                    datum.direction,
                    rows[0] if abs(rows[0] @ unit(datum.direction)) < 0.9 else rows[1],
                )
            )
            e2 = np.cross(unit(datum.direction), e1)
            for e in (e1, e2):
                equations.append(e)
                values.append(float(e @ datum.point))
    matrix = np.asarray(equations).reshape(-1, 3)
    singular = np.linalg.svd(matrix, compute_uv=False) if len(matrix) else np.zeros(0)
    rank = int((singular > PARALLEL_SIN).sum())
    if require_point and rank < 3:
        raise FrameError("alignment.noPoint")
    # Least-squares point on the datums, then free directions to the bounding-box minimum.
    point = (
        np.linalg.lstsq(matrix, np.asarray(values), rcond=None)[0] if len(matrix) else np.zeros(3)
    )
    local = vertices @ rows.T
    minimum = local.min(axis=0)
    for axis in range(3):
        fixed = bool(len(matrix)) and np.linalg.norm(matrix @ rows[axis]) > PARALLEL_SIN
        if not fixed:
            point = point + (minimum[axis] - point @ rows[axis]) * rows[axis]
    return np.asarray(point, dtype=np.float64)


def adjustment_rotation(adjust: AlignmentAdjust) -> FloatArray:
    """Rotation applied in part coordinates: flips turn the part by 180 degrees."""
    rotation = np.eye(3)
    if adjust.flip_z:
        rotation = np.diag([1.0, -1.0, -1.0]) @ rotation
    if adjust.flip_x:
        rotation = np.diag([-1.0, -1.0, 1.0]) @ rotation
    quarter = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    for _ in range(adjust.rotate_z90 % 4):
        rotation = quarter @ rotation
    return rotation


def angle_deg(a: FloatArray, b: FloatArray) -> float:
    return float(np.degrees(np.arccos(np.clip(abs(float(unit(a) @ unit(b))), -1.0, 1.0))))
