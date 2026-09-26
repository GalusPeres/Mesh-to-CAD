"""Automatic segmentation into regions of single primitives.

Pipeline (`.work/research/algorithms-mesh.md` 2.6), run on a 200 k-face copy:

1. Seeds far from crease zones first; a curvature-homogeneous start patch picks the
   type with `fit_best`; fit-filter-connect extracts the surface from free faces.
   A second pass with a smaller start radius picks up narrow features.
2. Crease faces and leftovers take the label of the neighbour with the most
   similar normal.
3. Border relaxation: border faces take the neighbouring label whose primitive is
   closest, wave by wave.
4. Residual pass: patches far from their own primitive get their own fit.
5. Merge pass: adjacent regions merge when one primitive explains both parts.

The labels are transferred to the full mesh by nearest centroid and relaxed there.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.codes.regions import ProgressStage
from m2c_kernel.fitting.api import (
    PRIMITIVE_KINDS,
    FitError,
    FitResult,
    PrimitiveKind,
    fit_best,
    fit_primitive,
    robust_sigma,
    signed_distance,
)
from m2c_kernel.segmentation.analysis import BoolArray, IntArray, MeshAnalysis, analyse
from m2c_kernel.segmentation.grow import auto_kinds, grow_primitive

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.session.jobs import JobContext

LOD_FACES = 200_000
SEED_RADII_MM = (3.0, 1.5)
MAX_ANGLE_DEG = 10.0
MERGE_SAMPLE = 5_000
_CHECK_INTERVAL_S = 0.1


@dataclass(frozen=True)
class AutoSegmentation:
    """Label per face of the input mesh (-1 = unassigned) and the primitive per label."""

    labels: IntArray
    fits: list[FitResult]


@dataclass(frozen=True)
class Tuning:
    """Thresholds derived from the sensitivity (0 = few large regions, 100 = many)."""

    tolerance_factor: float
    merge_factor: float
    min_area: float

    @classmethod
    def from_sensitivity(cls, sensitivity: float, min_area: float) -> Tuning:
        s = min(max(sensitivity, 0.0), 100.0) / 100.0
        return cls(tolerance_factor=6.0 - 4.0 * s, merge_factor=1.8 - s, min_area=min_area)


class _Checkpoint:
    """Calls `check_cancelled` at most every 100 ms (cheap to call in tight loops)."""

    def __init__(self, job: JobContext) -> None:
        self._job = job
        self._last = time.monotonic()

    def __call__(self) -> None:
        now = time.monotonic()
        if now - self._last >= _CHECK_INTERVAL_S:
            self._last = now
            self._job.check_cancelled()


# --------------------------------------------------------------------------------------
# Level of detail
# --------------------------------------------------------------------------------------

_LOD_CACHE: OrderedDict[str, EvalMesh] = OrderedDict()
_LOD_CAPACITY = 2


def level_of_detail(mesh: EvalMesh, job: JobContext) -> EvalMesh:
    """The mesh reduced to about 200 k faces, cached per mesh key (the mesh itself if small)."""
    if len(mesh.faces) <= LOD_FACES * 1.2:
        return mesh
    cached = _LOD_CACHE.get(mesh.key)
    if cached is not None:
        _LOD_CACHE.move_to_end(mesh.key)
        return cached
    import fast_simplification

    from m2c_kernel.document.rebuild import EvalMesh as _EvalMesh

    usable = ~mesh.synthetic
    faces = mesh.faces[usable]
    with job.native(ProgressStage.REDUCING):
        vertices, reduced = fast_simplification.simplify(
            mesh.vertices.astype(np.float32),
            faces.astype(np.int32),
            target_reduction=1.0 - LOD_FACES / len(faces),
            agg=5,
        )
    used = np.unique(reduced)
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    lod = _EvalMesh(
        f"{mesh.key}:lod",
        np.asarray(vertices, dtype=np.float64)[used],
        remap[np.asarray(reduced, dtype=np.int64)],
        None,
    )
    _LOD_CACHE[mesh.key] = lod
    while len(_LOD_CACHE) > _LOD_CAPACITY:
        _LOD_CACHE.popitem(last=False)
    return lod


# --------------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------------


def segment_mesh(
    mesh: EvalMesh,
    tuning: Tuning,
    job: JobContext,
    rng: np.random.Generator,
    within: BoolArray | None = None,
) -> AutoSegmentation:
    """Segment `mesh` (faces outside `within` stay unassigned)."""
    check = _Checkpoint(job)
    job.progress(None, ProgressStage.ANALYSING)
    lod = level_of_detail(mesh, job)
    job.check_cancelled()
    lod_within = None
    if within is not None:
        lod_within = within if lod is mesh else _transfer_mask(mesh, lod, within)
    analysis = analyse(lod)
    _ = analysis.crease, analysis.dominant_curvature, analysis.face_normals
    job.check_cancelled()

    labels, fits = _extract_regions(analysis, tuning, job, check, rng, lod_within)
    labels = _fill_unassigned(analysis, labels, len(fits), check, lod_within)
    labels = relax_boundaries(analysis, labels, fits, check)
    labels, fits = _add_unexplained(analysis, labels, fits, tuning, check, rng)
    labels, fits = _merge_regions(analysis, labels, fits, tuning, check, rng)
    labels = relax_boundaries(analysis, labels, fits, check)

    if lod is not mesh:
        job.progress(None, ProgressStage.TRANSFERRING)
        full = analyse(mesh)
        _, nearest = analysis.centroid_tree.query(mesh.face_centroids, workers=-1)
        labels = labels[nearest]
        if within is not None:
            labels[~within] = -1
        labels = relax_boundaries(full, labels, fits, check)
    labels[mesh.synthetic] = -1
    return _compact(labels, fits)


def _transfer_mask(mesh: EvalMesh, lod: EvalMesh, mask: BoolArray) -> BoolArray:
    _, nearest = analyse(mesh).centroid_tree.query(lod.face_centroids, workers=-1)
    result: BoolArray = mask[nearest]
    return result


def _extract_regions(
    analysis: MeshAnalysis,
    tuning: Tuning,
    job: JobContext,
    check: _Checkpoint,
    rng: np.random.Generator,
    within: BoolArray | None,
) -> tuple[IntArray, list[FitResult]]:
    mesh, graph = analysis.mesh, analysis.graph
    area = mesh.face_areas
    crease = analysis.crease
    tolerance = tuning.tolerance_factor * analysis.noise
    depth = _ring_distance(analysis, crease, check)
    pool = analysis.usable.copy() if within is None else analysis.usable & within
    free = pool & ~crease
    total_area = max(float(area[pool].sum()), 1e-12)
    labels = np.full(analysis.face_count, -1, dtype=np.int64)
    fits: list[FitResult] = []
    tree, centroids = analysis.centroid_tree, mesh.face_centroids
    order = np.argsort(-depth, kind="stable")
    for radius in SEED_RADII_MM:
        tried = np.zeros(analysis.face_count, dtype=bool)
        for seed in order:
            if depth[seed] < 2:
                break
            if not free[seed] or tried[seed]:
                continue
            check()
            local = np.asarray(tree.query_ball_point(centroids[seed], radius), dtype=np.int64)
            k = analysis.dominant_curvature
            ok = free[local] & (np.abs(k[local] - k[seed]) < max(0.03, 0.3 * abs(float(k[seed]))))
            allowed = np.zeros(analysis.face_count, dtype=bool)
            allowed[local[ok]] = True
            allowed[seed] = True
            patch = graph.grow(seed, allowed=allowed)
            if area[patch].sum() < 0.5 * np.pi * radius**2:
                tried[tree.query_ball_point(centroids[seed], 0.5 * radius)] = True
                continue
            tried |= patch
            try:
                kind = _fit_patch(analysis, patch, rng).kind
            except FitError:
                continue
            grown = grow_primitive(
                analysis,
                int(seed),
                patch,
                kind,
                tolerance,
                MAX_ANGLE_DEG,
                rng,
                allowed=free | (crease & pool & (labels < 0)),
                relaxed=crease,
                check=check,
            )
            region = grown.region & (labels < 0) & pool
            if grown.fit is None or area[region].sum() < tuning.min_area:
                continue
            labels[region] = len(fits)
            fits.append(grown.fit)
            free &= ~region
            tried |= region
            job.progress(
                min(float(area[labels >= 0].sum()) / total_area, 0.99), ProgressStage.GROWING
            )
    return labels, fits


def _fit_patch(analysis: MeshAnalysis, patch: BoolArray, rng: np.random.Generator) -> FitResult:
    vertices = np.unique(analysis.mesh.faces[patch])
    return fit_best(
        analysis.mesh.vertices[vertices],
        analysis.vertex_normals[vertices],
        rng,
        noise=analysis.noise,
        kinds=auto_kinds(analysis, patch),
    )[0]


def _ring_distance(analysis: MeshAnalysis, sources: BoolArray, check: _Checkpoint) -> IntArray:
    """Face rings to the nearest source face; unreachable faces count as far away."""
    neighbours = analysis.graph.neighbours
    distance = np.full(analysis.face_count, -1, dtype=np.int64)
    frontier = np.nonzero(sources)[0]
    distance[frontier] = 0
    ring = 0
    while len(frontier):
        check()
        ring += 1
        reached = neighbours[frontier].ravel()
        reached = np.unique(reached[reached >= 0])
        frontier = reached[distance[reached] < 0]
        distance[frontier] = ring
    distance[distance < 0] = ring + 1
    return distance


def _fill_unassigned(
    analysis: MeshAnalysis,
    labels: IntArray,
    fit_count: int,
    check: _Checkpoint,
    within: BoolArray | None,
) -> IntArray:
    """Unassigned faces take the label of the neighbour with the most similar normal."""
    labels = labels.copy()
    pairs, normals = analysis.graph.pairs, analysis.face_normals
    a = np.r_[pairs[:, 0], pairs[:, 1]]
    b = np.r_[pairs[:, 1], pairs[:, 0]]
    target = analysis.usable if within is None else analysis.usable & within
    for _ in range(500):
        check()
        mask = (labels[a] < 0) & (labels[b] >= 0) & target[a]
        if not mask.any():
            break
        u, v = a[mask], b[mask]
        order = np.lexsort((-(normals[u] * normals[v]).sum(axis=1), u))
        first = np.unique(u[order], return_index=True)[1]
        labels[u[order][first]] = labels[v[order][first]]
    orphan = (labels < 0) & target
    if orphan.any() and fit_count:
        # islands behind non-manifold edges join the nearest region if it is close
        assigned = np.nonzero(labels >= 0)[0]
        if len(assigned):
            from scipy.spatial import cKDTree

            centroids = analysis.mesh.face_centroids
            distance, index = cKDTree(centroids[assigned]).query(centroids[orphan], workers=-1)
            rows = np.nonzero(orphan)[0]
            close = distance < SEED_RADII_MM[0]
            labels[rows[close]] = labels[assigned[index[close]]]
    return labels


def relax_boundaries(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    check: _Checkpoint,
    max_waves: int = 300,
) -> IntArray:
    """Move region borders to where the fitted primitives meet."""
    labels = labels.copy()
    neighbours = analysis.graph.neighbours
    centroids = analysis.mesh.face_centroids
    count = len(fits)
    for _ in range(max_waves):
        check()
        neighbour_labels = np.where(neighbours >= 0, labels[np.maximum(neighbours, 0)], -1)
        border = (
            ((neighbour_labels != labels[:, None]) & (neighbour_labels >= 0)).any(axis=1)
            & (labels >= 0)
            & (labels < count)
        )
        index = np.nonzero(border)[0]
        if len(index) == 0:
            break
        candidates = np.column_stack([labels[index], neighbour_labels[index]])
        best_distance = np.full(len(index), np.inf)
        best_label = labels[index].copy()
        for column in candidates.T:
            for label in np.unique(column[(column >= 0) & (column < count)]):
                rows = np.nonzero(column == label)[0]
                distance = np.abs(signed_distance(fits[label].primitive, centroids[index[rows]]))
                better = distance < best_distance[rows]
                best_distance[rows[better]] = distance[better]
                best_label[rows[better]] = label
        if np.array_equal(best_label, labels[index]):
            break
        labels[index] = best_label
    return labels


def _face_residuals(analysis: MeshAnalysis, labels: IntArray, fits: list[FitResult]) -> np.ndarray:
    centroids = analysis.mesh.face_centroids
    residual = np.full(len(labels), np.inf)
    order = np.argsort(labels, kind="stable")
    bounds = np.searchsorted(labels[order], np.arange(len(fits) + 1))
    for label, fit in enumerate(fits):
        members = order[bounds[label] : bounds[label + 1]]
        residual[members] = np.abs(signed_distance(fit.primitive, centroids[members]))
    return residual


def _add_unexplained(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    tuning: Tuning,
    check: _Checkpoint,
    rng: np.random.Generator,
    accept: float = 1.5,
) -> tuple[IntArray, list[FitResult]]:
    """Connected patches far from their own primitive become regions if one fit explains them."""
    tolerance = tuning.tolerance_factor * analysis.noise
    area = analysis.mesh.face_areas
    bad = (_face_residuals(analysis, labels, fits) > tolerance) & analysis.usable
    bad &= labels >= 0
    if not bad.any():
        return labels, fits
    components = analysis.graph.components(bad)
    ids, inverse = np.unique(components[bad], return_inverse=True)
    component_area = np.bincount(inverse, weights=area[bad])
    fits = list(fits)
    for position in np.argsort(-component_area):
        if component_area[position] < max(tuning.min_area, 2.0):
            break
        check()
        members = components == ids[position]
        try:
            vertices = np.unique(analysis.mesh.faces[members])
            fit = fit_best(
                analysis.mesh.vertices[vertices],
                analysis.vertex_normals[vertices],
                rng,
                noise=analysis.noise,
            )[0]
        except FitError:
            continue
        if fit.sigma < accept * analysis.noise:
            labels = np.where(members, len(fits), labels)
            fits.append(fit)
    return labels, fits


def _merge_regions(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    tuning: Tuning,
    check: _Checkpoint,
    rng: np.random.Generator,
) -> tuple[IntArray, list[FitResult | None]] | tuple[IntArray, list[FitResult]]:
    """Merge adjacent regions whose union one primitive explains (both parts below the limit)."""
    mesh, pairs = analysis.mesh, analysis.graph.pairs
    limit = tuning.merge_factor * analysis.noise
    slots: list[FitResult | None] = list(fits)
    count = len(slots)
    while count > 1:
        order = np.argsort(labels, kind="stable")
        bounds = np.searchsorted(labels[order], np.arange(count + 1))
        la, lb = labels[pairs[:, 0]], labels[pairs[:, 1]]
        mask = (la != lb) & (la >= 0) & (lb >= 0)
        low, high = np.minimum(la[mask], lb[mask]), np.maximum(la[mask], lb[mask])
        keys, shared = np.unique(low * count + high, return_counts=True)
        touched: set[int] = set()
        merged = 0
        for key in keys[np.argsort(-shared)]:
            check()
            ra, rb = int(key // count), int(key % count)
            fit_a, fit_b = slots[ra], slots[rb]
            if ra in touched or rb in touched or fit_a is None or fit_b is None:
                continue
            part_a = _sample(mesh, analysis, order[bounds[ra] : bounds[ra + 1]], rng)
            part_b = _sample(mesh, analysis, order[bounds[rb] : bounds[rb + 1]], rng)
            points = np.vstack([part_a[0], part_b[0]])
            normals = np.vstack([part_a[1], part_b[1]])
            for kind in dict.fromkeys([fit_a.kind, fit_b.kind]):
                union = _try_fit(kind, points, normals, rng)
                if union is None:
                    continue
                sigma_a = robust_sigma(signed_distance(union.primitive, part_a[0]))
                sigma_b = robust_sigma(signed_distance(union.primitive, part_b[0]))
                if max(sigma_a, sigma_b) < limit:
                    labels = np.where(labels == rb, ra, labels)
                    slots[ra], slots[rb] = union, None
                    touched.update((ra, rb))
                    merged += 1
                    break
        if merged == 0:
            break
    return _drop_empty(labels, slots)


def _sample(
    mesh: EvalMesh, analysis: MeshAnalysis, members: IntArray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    chosen = rng.choice(members, min(len(members), MERGE_SAMPLE), replace=False)
    vertices = mesh.faces[chosen, 0]
    return mesh.vertices[vertices], analysis.vertex_normals[vertices]


def _try_fit(
    kind: PrimitiveKind, points: np.ndarray, normals: np.ndarray, rng: np.random.Generator
) -> FitResult | None:
    try:
        return fit_primitive(kind, points, normals, rng)
    except FitError:
        return None


def _drop_empty(labels: IntArray, slots: list[FitResult | None]) -> tuple[IntArray, list[FitResult]]:
    keep = [index for index, fit in enumerate(slots) if fit is not None]
    remap = np.full(len(slots) + 1, -1, dtype=np.int64)
    remap[keep] = np.arange(len(keep))
    result = np.where(labels >= 0, remap[np.maximum(labels, 0)], -1)
    return result, [fit for fit in slots if fit is not None]


def _compact(labels: IntArray, fits: list[FitResult]) -> AutoSegmentation:
    """Drop labels without faces; order regions by decreasing face count."""
    counts = np.bincount(labels[labels >= 0], minlength=len(fits))
    order = [int(i) for i in np.argsort(-counts, kind="stable") if counts[i] > 0]
    remap = np.full(len(fits) + 1, -1, dtype=np.int64)
    remap[order] = np.arange(len(order))
    result = np.where(labels >= 0, remap[np.maximum(labels, 0)], -1)
    return AutoSegmentation(result, [fits[i] for i in order])


__all__ = ["PRIMITIVE_KINDS", "AutoSegmentation", "Tuning", "level_of_detail", "segment_mesh"]
