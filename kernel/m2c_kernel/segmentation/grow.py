"""Seed-based region growing (smart select) in three modes.

- `primitive`: fit -> filter (distance and normal) -> connect -> refit, until the
  region stops changing. Finds one surface of a primitive type.
- `smooth`: crosses an edge while the adjacent normals differ by less than the
  angle; crease-zone faces are a barrier. Finds a tangent-continuous patch.
- `normal`: every connected face within the angle of the seed normal (planes).

Measurements: `.work/research/algorithms-mesh.md` 2.5.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.api import (
    PRIMITIVE_KINDS,
    FitError,
    FitResult,
    PrimitiveKind,
    fit_best,
    fit_primitive,
    signed_distance,
    surface_normals,
)
from m2c_kernel.segmentation.analysis import BoolArray, IntArray, MeshAnalysis

START_RADIUS_MM = 3.0
"""Radius of the start patch; cones and tori need a wider one."""
WIDE_START_RADIUS_MM = 5.0
FLAT_CURVATURE = 0.03
"""A patch with a larger median |curvature| (1/mm) may not become a plane."""
MAX_ROUNDS = 12
FIT_SAMPLE = 20_000


@dataclass(frozen=True)
class Grown:
    region: BoolArray
    fit: FitResult | None


def similar_curvature(analysis: MeshAnalysis, seed: int) -> BoolArray:
    k = analysis.dominant_curvature
    result: BoolArray = np.abs(k - k[seed]) < max(0.03, 0.3 * abs(float(k[seed])))
    return result


def start_patch(
    analysis: MeshAnalysis, seed: int, radius: float, allowed: BoolArray | None = None
) -> BoolArray:
    """Connected faces around the seed within `radius` with a similar curvature."""
    near = np.asarray(
        analysis.centroid_tree.query_ball_point(analysis.mesh.face_centroids[seed], radius),
        dtype=np.int64,
    )
    mask = np.zeros(analysis.face_count, dtype=bool)
    mask[near] = True
    mask &= similar_curvature(analysis, seed) & analysis.usable
    if allowed is not None:
        mask &= allowed
    mask[seed] = True
    return analysis.graph.grow(seed, allowed=mask)


def fit_faces(
    analysis: MeshAnalysis,
    region: BoolArray | IntArray,
    kind: PrimitiveKind | None,
    rng: np.random.Generator,
    kinds: tuple[PrimitiveKind, ...] = PRIMITIVE_KINDS,
) -> FitResult:
    """Fit the vertices of the faces (kind None: choose the type automatically)."""
    mesh = analysis.mesh
    vertices = np.unique(mesh.faces[region])
    if len(vertices) > FIT_SAMPLE:
        vertices = rng.choice(vertices, FIT_SAMPLE, replace=False)
    points, normals = mesh.vertices[vertices], analysis.vertex_normals[vertices]
    if kind is not None:
        return fit_primitive(kind, points, normals, rng)
    return fit_best(points, normals, rng, noise=analysis.noise, kinds=kinds)[0]


def auto_kinds(analysis: MeshAnalysis, patch: BoolArray) -> tuple[PrimitiveKind, ...]:
    """Candidate types for a start patch: a clearly curved patch is never a plane."""
    curved = float(np.median(np.abs(analysis.dominant_curvature[patch]))) > FLAT_CURVATURE
    return tuple(kind for kind in PRIMITIVE_KINDS if not (curved and kind == "plane"))


def grow_primitive(
    analysis: MeshAnalysis,
    seed: int,
    start: BoolArray,
    kind: PrimitiveKind,
    tolerance: float,
    max_angle_deg: float,
    rng: np.random.Generator,
    allowed: BoolArray | None = None,
    relaxed: BoolArray | None = None,
    check: Callable[[], None] | None = None,
) -> Grown:
    """Fit-filter-connect from a start patch; faces in `relaxed` need only the distance test."""
    mesh = analysis.mesh
    centroids, normals = mesh.face_centroids, analysis.face_normals
    pool = analysis.usable if allowed is None else allowed & analysis.usable
    candidates = np.nonzero(pool)[0]
    cos_limit = np.cos(np.radians(max_angle_deg))
    region, fit = start, None
    for _ in range(MAX_ROUNDS):
        if check is not None:
            check()
        try:
            fit = fit_faces(analysis, region, kind, rng)
        except FitError:
            break
        distance = signed_distance(fit.primitive, centroids[candidates])
        near = candidates[np.abs(distance) < tolerance]
        surface = surface_normals(fit.primitive, centroids[near])
        ok = np.abs((surface * normals[near]).sum(axis=1)) >= cos_limit
        if relaxed is not None:
            ok |= relaxed[near]
        accepted = np.zeros(analysis.face_count, dtype=bool)
        accepted[near[ok]] = True
        accepted[seed] = True
        grown = analysis.graph.grow(seed, allowed=accepted)
        changed = int(np.count_nonzero(grown ^ region))
        region = grown
        if changed <= max(10, 1e-4 * int(region.sum())):
            break
    return Grown(region, fit)


def grow_smooth(analysis: MeshAnalysis, seed: int, max_angle_deg: float) -> BoolArray:
    pairs = analysis.graph.pairs
    normals = analysis.face_normals
    ok = (normals[pairs[:, 0]] * normals[pairs[:, 1]]).sum(axis=1) > np.cos(
        np.radians(max_angle_deg)
    )
    barrier = analysis.crease.copy()
    barrier[seed] = False
    return analysis.graph.grow(seed, allowed=~barrier & analysis.usable, pair_allowed=ok)


def grow_normal(analysis: MeshAnalysis, seed: int, max_angle_deg: float) -> BoolArray:
    normals = analysis.face_normals
    allowed: npt.NDArray[np.bool_] = normals @ normals[seed] > np.cos(np.radians(max_angle_deg))
    allowed &= analysis.usable
    allowed[seed] = True
    return analysis.graph.grow(seed, allowed=allowed)
