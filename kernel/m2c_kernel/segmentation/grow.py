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
from m2c_kernel.geometry import FloatArray
from m2c_kernel.segmentation.analysis import BoolArray, IntArray, MeshAnalysis

START_RADIUS_MM = 3.0
"""Radius of the start patch; cones and tori need a wider one."""
WIDE_START_RADIUS_MM = 5.0
CURVATURE_TOLERANCE = 0.04
"""Smoothed curvatures (1/mm) of one surface scatter by about +-0.02 on a 0.03 mm noise scan."""
RELATIVE_CURVATURE_TOLERANCE = 0.3
SEED_CREASE_REACH_MM = 1.0
FLAT_CURVATURE = 0.03
"""A patch with a larger median |curvature| (1/mm) may not become a plane."""
SIMPLER_TYPE_MARGIN = 1.15
"""A simpler type replaces a fit when its robust sigma is at most this factor higher
(the same rule `fit_best` uses to choose between types)."""
MAX_ROUNDS = 12
FIT_SAMPLE = 20_000
TRIAL_SAMPLE = 4_000


@dataclass(frozen=True)
class Grown:
    region: BoolArray
    fit: FitResult | None


def start_patch(
    analysis: MeshAnalysis,
    seed: int,
    radius: float,
    allowed: BoolArray | None = None,
    widen: bool = True,
) -> BoolArray:
    """Connected faces around the seed within `radius` with a curvature similar to the seed's.

    Crease-zone faces are left out, so the patch stays on the surface of the seed
    even when the seed lies close to an edge. A seed inside a small crease
    fragment (a noise spike) may cross crease faces within 1 mm to reach its
    surface. With `widen`, a patch that covers less than half the disc is built
    again with twice the curvature limit (narrow bands such as chamfers).
    """
    centroids = analysis.mesh.face_centroids
    near = np.asarray(
        analysis.centroid_tree.query_ball_point(centroids[seed], radius), dtype=np.int64
    )
    curvature = analysis.dominant_curvature
    reference = float(curvature[seed])
    base = analysis.usable[near] & ~analysis.crease[near]
    if analysis.crease[seed]:
        close = np.linalg.norm(centroids[near] - centroids[seed], axis=1) < SEED_CREASE_REACH_MM
        base |= close & analysis.usable[near]
    if allowed is not None:
        base &= allowed[near]
    limit = max(CURVATURE_TOLERANCE, RELATIVE_CURVATURE_TOLERANCE * abs(reference))
    area = analysis.mesh.face_areas
    patch = np.zeros(analysis.face_count, dtype=bool)
    for factor in (1.0, 2.0) if widen else (1.0,):
        ok = base & (np.abs(curvature[near] - reference) < factor * limit)
        mask = np.zeros(analysis.face_count, dtype=bool)
        mask[near[ok]] = True
        mask[seed] = True
        patch = analysis.graph.grow(seed, allowed=mask)
        if area[patch].sum() >= 0.5 * np.pi * radius**2:
            break
    return patch


def region_points(
    analysis: MeshAnalysis,
    region: BoolArray | IntArray,
    rng: np.random.Generator,
    limit: int = FIT_SAMPLE,
) -> tuple[FloatArray, FloatArray]:
    """Vertices of the region's faces with their jet normals (a random subset above `limit`)."""
    mesh = analysis.mesh
    vertices = np.unique(mesh.faces[region])
    if len(vertices) > limit:
        vertices = rng.choice(vertices, limit, replace=False)
    return mesh.vertices[vertices], analysis.vertex_normals[vertices]


def fit_faces(
    analysis: MeshAnalysis,
    region: BoolArray | IntArray,
    kind: PrimitiveKind | None,
    rng: np.random.Generator,
    kinds: tuple[PrimitiveKind, ...] = PRIMITIVE_KINDS,
) -> FitResult:
    """Fit the vertices of the faces (kind None: choose the type automatically)."""
    points, normals = region_points(analysis, region, rng)
    if kind is not None:
        return fit_primitive(kind, points, normals, rng)
    return fit_best(points, normals, rng, noise=analysis.noise, kinds=kinds)[0]


def auto_kinds(analysis: MeshAnalysis, patch: BoolArray) -> tuple[PrimitiveKind, ...]:
    """Candidate types for a start patch: a clearly curved patch is never a plane.

    Along the axis of a fillet a narrow plane fits within the noise, so the
    curvature has to rule it out.
    """
    curved = float(np.median(np.abs(analysis.dominant_curvature[patch]))) > FLAT_CURVATURE
    return tuple(kind for kind in PRIMITIVE_KINDS if not (curved and kind == "plane"))


def simplest_fit(
    analysis: MeshAnalysis, region: BoolArray, fit: FitResult, rng: np.random.Generator
) -> FitResult:
    """Replace the fit by a simpler type that explains the region as well.

    A plane grown as a sphere of radius 90 m, or a cylinder grown as a torus with
    a huge major radius, is reported as the simpler type.
    """
    position = PRIMITIVE_KINDS.index(fit.kind)
    if position == 0:
        return fit
    points, normals = region_points(analysis, region, rng, TRIAL_SAMPLE)
    try:
        reference = fit_primitive(fit.kind, points, normals, rng).sigma
    except FitError:
        # a cone or torus fit that degenerates on the final region is itself a sign
        # that a simpler type describes it
        reference = fit.sigma
    for kind in PRIMITIVE_KINDS[:position]:
        try:
            trial = fit_primitive(kind, points, normals, rng)
        except FitError:
            continue
        if trial.sigma <= SIMPLER_TYPE_MARGIN * reference:
            try:
                return fit_faces(analysis, region, kind, rng)
            except FitError:
                return fit
    return fit


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
    """Fit-filter-connect from a start patch; faces in `relaxed` need only the distance test.

    Each round fits the primitive to the region, keeps the candidate faces within
    `tolerance` of it whose normal agrees within `max_angle_deg`, and keeps the
    part connected to the seed. It stops when the region changes by less than
    0.01 % (at least 10 faces).
    """
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
    """Faces reachable across edges whose adjacent normals differ by less than the angle."""
    pairs = analysis.graph.pairs
    normals = analysis.face_normals
    ok = (normals[pairs[:, 0]] * normals[pairs[:, 1]]).sum(axis=1) > np.cos(
        np.radians(max_angle_deg)
    )
    barrier = analysis.crease.copy()
    barrier[seed] = False
    return analysis.graph.grow(seed, allowed=~barrier & analysis.usable, pair_allowed=ok)


def grow_normal(analysis: MeshAnalysis, seed: int, max_angle_deg: float) -> BoolArray:
    """Connected faces whose normal lies within the angle of the seed normal."""
    normals = analysis.face_normals
    allowed: BoolArray = normals @ normals[seed] > np.cos(np.radians(max_angle_deg))
    allowed &= analysis.usable
    allowed[seed] = True
    return analysis.graph.grow(seed, allowed=allowed)
