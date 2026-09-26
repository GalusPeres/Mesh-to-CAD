"""B-spline patches fitted to scan regions as height fields.

The region's points are expressed in a frame whose `w` axis is the mean surface
normal; `w(u, v)` is fitted as a bicubic tensor B-spline by penalised least squares
(P-spline, Eilers and Marx): `|A c - w|^2 + lambda (|D_u c|^2 + |D_v c|^2)` with
second differences of the coefficient grid. The penalty keeps the system well posed
over holes and in the corners of the parameter rectangle where the scan has no data.

The result converts exactly to an Open CASCADE B-spline surface: the poles are
`(greville_u[i], greville_v[j], c[i, j])` mapped to part coordinates, because
Greville abscissae reproduce linear functions and the frame map is affine.
Measurements: `.work/research/algorithms-cad.md` 3.1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.interpolate import BSpline
from scipy.sparse.linalg import spsolve

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.geometry import FloatArray, unit
from m2c_kernel.protocol.errors import KernelError

DEGREE = 3
SPAN_LENGTH_MM = 5.0
"""Automatic span count: about one span per 5 mm of extent."""
MIN_SPANS = 2
MAX_SPANS = 64
REFINE_FACTOR = 1.5
REFINE_GAIN = 0.05
"""Automatic refinement continues while the RMS falls by more than 5 % per step."""
MAX_NORMAL_SPREAD_DEG = 150.0
"""A height field needs all normals within a cone; wider regions need a loft or a split."""
MIN_POINTS = 16

type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class PatchFrame:
    """Origin and axes (rows u, v, w) of the height field; `w` is the mean normal."""

    origin: FloatArray
    axes: FloatArray

    def local(self, points: FloatArray) -> FloatArray:
        result: FloatArray = (points - self.origin) @ self.axes.T
        return result

    def world(self, local: FloatArray) -> FloatArray:
        result: FloatArray = self.origin + np.asarray(local) @ self.axes
        return result


@dataclass(frozen=True)
class HeightField:
    """A bicubic tensor B-spline `w(u, v)` in a patch frame."""

    frame: PatchFrame
    knots_u: FloatArray
    knots_v: FloatArray
    coefficients: FloatArray
    """(nu, nv) coefficient grid."""

    @property
    def spans(self) -> tuple[int, int]:
        return (len(np.unique(self.knots_u)) - 1, len(np.unique(self.knots_v)) - 1)

    @property
    def domain(self) -> tuple[float, float, float, float]:
        """Parameter rectangle (u0, u1, v0, v1) in millimetres of the frame."""
        return (
            float(self.knots_u[0]),
            float(self.knots_u[-1]),
            float(self.knots_v[0]),
            float(self.knots_v[-1]),
        )

    def height(self, u: FloatArray, v: FloatArray) -> FloatArray:
        design = tensor_design(u, v, self.knots_u, self.knots_v)
        result: FloatArray = design @ self.coefficients.ravel()
        return result

    def points(self, u: FloatArray, v: FloatArray) -> FloatArray:
        """Surface points in part coordinates."""
        return self.frame.world(np.column_stack([u, v, self.height(u, v)]))

    def normal_distance(self, points: FloatArray) -> FloatArray:
        """Signed distance along the surface normal, to first order.

        The vertical offset `w - w(u, v)` is scaled by the cosine of the local slope;
        for the gentle slopes of a height field this is within a fraction of a micron
        of the exact projection.
        """
        local = self.frame.local(points)
        u, v, w = local.T
        step = 1e-3
        du = (self.height(u + step, v) - self.height(u - step, v)) / (2 * step)
        dv = (self.height(u, v + step) - self.height(u, v - step)) / (2 * step)
        vertical = w - self.height(u, v)
        result: FloatArray = vertical / np.sqrt(1.0 + du * du + dv * dv)
        return result

    def greville(self) -> tuple[FloatArray, FloatArray]:
        return _greville(self.knots_u), _greville(self.knots_v)

    def poles(self) -> FloatArray:
        """(nu, nv, 3) control points in part coordinates (exact conversion)."""
        gu, gv = self.greville()
        uu, vv = np.meshgrid(gu, gv, indexing="ij")
        local = np.stack([uu, vv, self.coefficients], axis=-1)
        return self.frame.world(local.reshape(-1, 3)).reshape(*self.coefficients.shape, 3)


@dataclass(frozen=True)
class PatchFit:
    surface: HeightField
    rms: float
    max_abs: float
    normal_spread_deg: float
    point_count: int
    deviations: FloatArray
    """Signed normal distance of every input point."""


def patch_frame(points: FloatArray, normals: FloatArray) -> PatchFrame:
    """Frame with `w` along the mean normal and `u` along the longest in-plane extent."""
    w = unit(normals.sum(axis=0))
    if not np.any(w):
        raise KernelError(ErrorCode.TOO_CURVED, {"spreadDeg": 180.0})
    origin = points.mean(axis=0)
    helper = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = unit(np.cross(w, helper))
    e2 = np.cross(w, e1)
    planar = (points - origin) @ np.stack([e1, e2]).T
    _, vectors = np.linalg.eigh(planar.T @ planar)
    u = unit(vectors[0, -1] * e1 + vectors[1, -1] * e2)
    # A fixed sign rule keeps the frame the same for the same input.
    if float(u @ np.array([1.0, 0.7, 0.4])) < 0:
        u = -u
    return PatchFrame(origin, np.stack([u, np.cross(w, u), w]))


def normal_spread_deg(normals: FloatArray, w: FloatArray) -> float:
    """Opening angle of the cone around `w` that holds 99 % of the normals."""
    cosine = np.clip(normals @ w, -1.0, 1.0)
    return 2.0 * float(np.degrees(np.arccos(np.percentile(cosine, 1.0))))


def fit_patch(
    points: FloatArray,
    normals: FloatArray,
    spans: tuple[int, int] | None,
    smoothing: float,
    margin: float,
) -> PatchFit:
    """Fit a height-field patch; `spans` None chooses the span count automatically."""
    if len(points) < MIN_POINTS:
        raise KernelError(ErrorCode.FIT_FAILED)
    frame = patch_frame(points, unit(normals))
    spread = normal_spread_deg(unit(normals), frame.axes[2])
    if spread > MAX_NORMAL_SPREAD_DEG:
        raise KernelError(
            ErrorCode.TOO_CURVED,
            {"spreadDeg": round(spread, 1), "maxDeg": MAX_NORMAL_SPREAD_DEG},
        )
    local = frame.local(points)
    if spans is None:
        surface, deviations = _auto_spans(frame, local, smoothing, margin)
    else:
        surface = fit_height_field(frame, local, _clamped(spans), smoothing, margin)
        deviations = surface.normal_distance(points)
    return PatchFit(
        surface=surface,
        rms=float(np.sqrt(np.mean(deviations**2))),
        max_abs=float(np.abs(deviations).max()),
        normal_spread_deg=spread,
        point_count=len(points),
        deviations=deviations,
    )


def initial_spans(local: FloatArray, margin: float) -> tuple[int, int]:
    extent = np.ptp(local[:, :2], axis=0) + 2.0 * margin
    return _clamped(
        (math.ceil(float(extent[0]) / SPAN_LENGTH_MM), math.ceil(float(extent[1]) / SPAN_LENGTH_MM))
    )


def _auto_spans(
    frame: PatchFrame, local: FloatArray, smoothing: float, margin: float
) -> tuple[HeightField, FloatArray]:
    """Start at about 5 mm spans and refine while the RMS still falls noticeably."""
    points = frame.world(local)
    spans = initial_spans(local, margin)
    surface = fit_height_field(frame, local, spans, smoothing, margin)
    deviations = surface.normal_distance(points)
    rms = float(np.sqrt(np.mean(deviations**2)))
    while max(spans) < MAX_SPANS:
        finer = _clamped((math.ceil(spans[0] * REFINE_FACTOR), math.ceil(spans[1] * REFINE_FACTOR)))
        if finer == spans:
            break
        candidate = fit_height_field(frame, local, finer, smoothing, margin)
        candidate_deviations = candidate.normal_distance(points)
        candidate_rms = float(np.sqrt(np.mean(candidate_deviations**2)))
        if candidate_rms > (1.0 - REFINE_GAIN) * rms:
            break
        surface, deviations, rms, spans = candidate, candidate_deviations, candidate_rms, finer
    return surface, deviations


def _clamped(spans: tuple[int, int]) -> tuple[int, int]:
    return (
        min(MAX_SPANS, max(MIN_SPANS, int(spans[0]))),
        min(MAX_SPANS, max(MIN_SPANS, int(spans[1]))),
    )


def fit_height_field(
    frame: PatchFrame,
    local: FloatArray,
    spans: tuple[int, int],
    smoothing: float,
    margin: float,
) -> HeightField:
    """Penalised least squares on a fixed knot grid (P-spline)."""
    u, v, w = local.T
    knots_u = _clamped_knots(float(u.min()) - margin, float(u.max()) + margin, spans[0])
    knots_v = _clamped_knots(float(v.min()) - margin, float(v.max()) + margin, spans[1])
    nu, nv = len(knots_u) - DEGREE - 1, len(knots_v) - DEGREE - 1
    design = tensor_design(u, v, knots_u, knots_v)
    d_u = sp.kron(_second_difference(nu), sp.identity(nv))
    d_v = sp.kron(sp.identity(nu), _second_difference(nv))
    penalty = (d_u.T @ d_u + d_v.T @ d_v) * (smoothing * len(u) / (nu * nv))
    normal_matrix = (design.T @ design + penalty).tocsc()
    coefficients = np.asarray(spsolve(normal_matrix, design.T @ w), dtype=np.float64)
    if not np.all(np.isfinite(coefficients)):
        raise KernelError(ErrorCode.FIT_FAILED)
    return HeightField(frame, knots_u, knots_v, coefficients.reshape(nu, nv))


def tensor_design(
    u: FloatArray, v: FloatArray, knots_u: FloatArray, knots_v: FloatArray
) -> sp.csr_matrix:
    """Sparse design matrix A with `A[i, a * nv + b] = Bu_a(u_i) Bv_b(v_i)`."""
    bu = BSpline.design_matrix(np.clip(u, knots_u[0], knots_u[-1]), knots_u, DEGREE).tocsr()
    bv = BSpline.design_matrix(np.clip(v, knots_v[0], knots_v[-1]), knots_v, DEGREE).tocsr()
    k = DEGREE + 1
    n, nu, nv = len(u), bu.shape[1], bv.shape[1]
    iu, du = bu.indices.reshape(n, k), bu.data.reshape(n, k)
    iv, dv = bv.indices.reshape(n, k), bv.data.reshape(n, k)
    columns = (iu[:, :, None] * nv + iv[:, None, :]).reshape(n, k * k)
    values = (du[:, :, None] * dv[:, None, :]).reshape(n, k * k)
    rows = np.arange(0, n * k * k + 1, k * k)
    return sp.csr_matrix((values.ravel(), columns.ravel(), rows), shape=(n, nu * nv))


def _clamped_knots(low: float, high: float, spans: int) -> FloatArray:
    inner = np.linspace(low, high, spans + 1)
    return np.concatenate([[low] * DEGREE, inner, [high] * DEGREE])


def _second_difference(n: int) -> sp.dia_matrix:
    return sp.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n))


def _greville(knots: FloatArray) -> FloatArray:
    count = len(knots) - DEGREE - 1
    return np.array([knots[i + 1 : i + DEGREE + 1].mean() for i in range(count)])


def patch_grid(
    surface: HeightField, resolution: int = 48
) -> tuple[FloatArray, IntArray, FloatArray]:
    """Display mesh over the full parameter rectangle, and iso-lines every 10 %.

    Returns the vertices (n, 3), triangles (m, 3) and line segments (s, 2, 3).
    """
    u0, u1, v0, v1 = surface.domain
    us, vs = np.linspace(u0, u1, resolution), np.linspace(v0, v1, resolution)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    vertices = surface.points(uu.ravel(), vv.ravel())
    index = np.arange(resolution * resolution).reshape(resolution, resolution)
    a, b = index[:-1, :-1].ravel(), index[1:, :-1].ravel()
    c, d = index[1:, 1:].ravel(), index[:-1, 1:].ravel()
    triangles = np.concatenate([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    segments: list[FloatArray] = []
    samples = np.linspace(0.0, 1.0, resolution)
    for fraction in np.linspace(0.0, 1.0, 11):
        fixed_u = np.full(resolution, u0 + fraction * (u1 - u0))
        fixed_v = np.full(resolution, v0 + fraction * (v1 - v0))
        for line in (
            surface.points(fixed_u, v0 + samples * (v1 - v0)),
            surface.points(u0 + samples * (u1 - u0), fixed_v),
        ):
            segments.append(np.stack([line[:-1], line[1:]], axis=1))
    return vertices, triangles.astype(np.int64), np.concatenate(segments)
