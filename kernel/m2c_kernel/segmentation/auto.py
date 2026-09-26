"""Automatic segmentation into regions of single primitives.

Pipeline (`.work/research/algorithms-mesh.md` 2.6), run on a reduced copy of
large scans:

1. Seeds far from crease zones first; a curvature-homogeneous start patch picks the
   type with `fit_best`; fit-filter-connect extracts the surface from free faces.
   A second pass with a smaller start radius picks up narrow features.
2. Crease faces and leftovers take the label of the neighbour with the most
   similar normal.
3. Border relaxation: border faces take the neighbouring label whose primitive is
   closest, wave by wave.
4. Residual pass: patches far from their own primitive get their own fit.
5. Merge pass: adjacent regions merge when one primitive explains both parts.
6. Every region reports the simplest type that explains it.

The labels are transferred to the full mesh by nearest centroid and relaxed there.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial import cKDTree

from m2c_kernel.codes.regions import ProgressStage
from m2c_kernel.fitting.api import (
    FitError,
    FitResult,
    PrimitiveKind,
    fit_best,
    fit_primitive,
    robust_sigma,
    signed_distance,
)
from m2c_kernel.geometry import FloatArray
from m2c_kernel.segmentation.analysis import BoolArray, IntArray, MeshAnalysis, analyse
from m2c_kernel.segmentation.grow import (
    auto_kinds,
    fit_faces,
    grow_primitive,
    region_points,
    simplest_fit,
    start_patch,
)

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.session.jobs import JobContext

SEED_RADII_MM = (3.0, 1.5)
MAX_ANGLE_DEG = 10.0
MERGE_SAMPLE = 2_000
"""Faces sampled per region for the merge test (a robust sigma needs few points)."""
MERGE_PREFILTER = 10.0
RESIDUAL_ACCEPT = 1.5
"""A residual patch becomes a region when one fit explains it below this x the noise."""
MIN_RESIDUAL_AREA = 2.0
TRANSFER_CHUNK = 200_000
_CHECK_INTERVAL_S = 0.1

# Share of the progress bar per phase; growing is reported per accepted region.
_GROWING_END = 0.8
_REFINING_END = 0.95


@dataclass(frozen=True)
class AutoSegmentation:
    """Label per face of the input mesh (-1 = unassigned) and the primitive per label.

    `rms` is the RMS distance of each region's full-resolution vertices to its primitive.
    """

    labels: IntArray
    fits: list[FitResult]
    rms: list[float]


@dataclass(frozen=True)
class Tuning:
    """Thresholds derived from the sensitivity (0 = few large regions, 100 = many).

    Sensitivity 50 gives the values measured in the research notes: a growth
    tolerance of 4 x the noise and a merge limit of 1.3 x the noise.
    """

    tolerance_factor: float
    merge_factor: float
    min_area: float

    @classmethod
    def from_sensitivity(cls, sensitivity: float, min_area: float) -> Tuning:
        s = min(max(sensitivity, 0.0), 100.0) / 100.0
        return cls(
            tolerance_factor=6.0 - 4.0 * s, merge_factor=1.8 - s, min_area=max(min_area, 0.0)
        )


class Checkpoint:
    """Calls `check_cancelled` at most every 100 ms (cheap to call in tight loops)."""

    def __init__(self, job: JobContext) -> None:
        self._job = job
        self._last = time.monotonic()

    def __call__(self) -> None:
        now = time.monotonic()
        if now - self._last >= _CHECK_INTERVAL_S:
            self._last = now
            self._job.check_cancelled()


def segment_mesh(
    mesh: EvalMesh,
    lod: EvalMesh,
    tuning: Tuning,
    job: JobContext,
    rng: np.random.Generator,
    within: BoolArray | None = None,
) -> AutoSegmentation:
    """Segment `mesh`, working on its reduced copy `lod` (which may be `mesh` itself).

    Faces outside `within` and synthetic faces stay unassigned.
    """
    check = Checkpoint(job)
    job.progress(None, ProgressStage.ANALYSING)
    analysis = analyse(lod)
    analysis.warm_up(job.check_cancelled)
    lod_within = None
    if within is not None:
        lod_within = within if lod is mesh else _transfer_mask(mesh, lod, within, check)

    labels, fits = _extract_regions(analysis, tuning, job, check, rng, lod_within)
    job.progress(_GROWING_END, ProgressStage.REFINING)
    labels = _fill_unassigned(analysis, labels, len(fits), check, lod_within)
    labels = relax_boundaries(analysis, labels, fits, check)
    labels, fits = _add_unexplained(analysis, labels, fits, tuning, check, rng)
    labels, fits = _merge_regions(analysis, labels, fits, tuning, check, rng)
    labels = relax_boundaries(analysis, labels, fits, check)
    fits = _simplest_fits(analysis, labels, fits, check, rng)

    if lod is not mesh:
        job.progress(_REFINING_END, ProgressStage.TRANSFERRING)
        labels = _transfer_labels(analysis, mesh, labels, check)
        if within is not None:
            labels[~within] = -1
        labels = relax_boundaries(analyse(mesh), labels, fits, check)
    labels[mesh.synthetic] = -1
    labels, fits = _compact(labels, fits)
    return AutoSegmentation(labels, fits, _full_rms(mesh, labels, fits, rng))


def _transfer_mask(mesh: EvalMesh, lod: EvalMesh, mask: BoolArray, check: Checkpoint) -> BoolArray:
    """A face of the copy is inside when the nearest full-resolution face is."""
    nearest = _nearest(analyse(mesh).centroid_tree, lod.face_centroids, check)
    result: BoolArray = mask[nearest]
    return result


def _transfer_labels(
    analysis: MeshAnalysis, mesh: EvalMesh, labels: IntArray, check: Checkpoint
) -> IntArray:
    nearest = _nearest(analysis.centroid_tree, mesh.face_centroids, check)
    result: IntArray = labels[nearest]
    return result


def _nearest(tree: cKDTree, points: FloatArray, check: Checkpoint) -> IntArray:
    """Nearest tree point per query point, in chunks so cancellation stays responsive."""
    result = np.empty(len(points), dtype=np.int64)
    for start in range(0, len(points), TRANSFER_CHUNK):
        check()
        part = slice(start, start + TRANSFER_CHUNK)
        result[part] = tree.query(points[part], workers=-1)[1]
    return result


def _extract_regions(
    analysis: MeshAnalysis,
    tuning: Tuning,
    job: JobContext,
    check: Checkpoint,
    rng: np.random.Generator,
    within: BoolArray | None,
) -> tuple[IntArray, list[FitResult]]:
    mesh = analysis.mesh
    area = mesh.face_areas
    crease = analysis.crease
    tolerance = tuning.tolerance_factor * analysis.noise
    depth = _ring_distance(analysis, crease, check)
    pool = analysis.usable.copy() if within is None else analysis.usable & within
    free = pool & ~crease
    total_area = max(float(area[pool].sum()), 1e-12)
    assigned_area = 0.0
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
            patch = start_patch(analysis, int(seed), radius, allowed=free, widen=False)
            if area[patch].sum() < 0.5 * np.pi * radius**2:
                # a narrow strip along a fillet looks planar: no type decision here
                tried[tree.query_ball_point(centroids[seed], 0.5 * radius)] = True
                continue
            tried |= patch
            try:
                kind = fit_faces(analysis, patch, None, rng, auto_kinds(analysis, patch)).kind
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
            region_area = float(area[region].sum())
            if grown.fit is None or region_area < max(tuning.min_area, MIN_RESIDUAL_AREA):
                continue
            labels[region] = len(fits)
            fits.append(grown.fit)
            free &= ~region
            tried |= region
            assigned_area += region_area
            job.progress(_GROWING_END * min(assigned_area / total_area, 1.0), ProgressStage.GROWING)
    return labels, fits


def _ring_distance(analysis: MeshAnalysis, sources: BoolArray, check: Checkpoint) -> IntArray:
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
    check: Checkpoint,
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
    assigned = np.nonzero(labels >= 0)[0]
    if orphan.any() and fit_count and len(assigned):
        # islands behind non-manifold edges join the nearest region if it is close
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
    check: Checkpoint,
    max_waves: int = 300,
) -> IntArray:
    """Move region borders to where the fitted primitives meet.

    A face on a border takes the label (its own or a neighbour's) whose primitive
    is closest to its centroid; repeated wave by wave until nothing changes.
    """
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


def _members(labels: IntArray, count: int) -> list[IntArray]:
    """Face indices per label 0 .. count - 1."""
    order = np.argsort(labels, kind="stable")
    bounds = np.searchsorted(labels[order], np.arange(count + 1))
    return [order[bounds[label] : bounds[label + 1]] for label in range(count)]


def _face_residuals(analysis: MeshAnalysis, labels: IntArray, fits: list[FitResult]) -> FloatArray:
    centroids = analysis.mesh.face_centroids
    residual = np.full(len(labels), np.inf)
    for fit, members in zip(fits, _members(labels, len(fits)), strict=True):
        residual[members] = np.abs(signed_distance(fit.primitive, centroids[members]))
    return residual


def _add_unexplained(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    tuning: Tuning,
    check: Checkpoint,
    rng: np.random.Generator,
) -> tuple[IntArray, list[FitResult]]:
    """Connected patches far from their own primitive become regions if one fit explains them.

    This finds narrow features such as a 2 mm chamfer, whose seeds have too little
    clean area for the growing pass.
    """
    tolerance = tuning.tolerance_factor * analysis.noise
    area = analysis.mesh.face_areas
    bad = (_face_residuals(analysis, labels, fits) > tolerance) & analysis.usable & (labels >= 0)
    if not bad.any():
        return labels, fits
    components = analysis.graph.components(bad)
    ids, inverse = np.unique(components[bad], return_inverse=True)
    component_area = np.bincount(inverse, weights=area[bad])
    fits = list(fits)
    for position in np.argsort(-component_area):
        if component_area[position] < max(tuning.min_area, MIN_RESIDUAL_AREA):
            break
        check()
        members = components == ids[position]
        points, normals = region_points(analysis, members, rng)
        try:
            fit = fit_best(points, normals, rng, noise=analysis.noise)[0]
        except FitError:
            continue
        if fit.sigma < RESIDUAL_ACCEPT * analysis.noise:
            labels = np.where(members, len(fits), labels)
            fits.append(fit)
    return labels, fits


def _merge_regions(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    tuning: Tuning,
    check: Checkpoint,
    rng: np.random.Generator,
) -> tuple[IntArray, list[FitResult]]:
    """Merge adjacent regions whose union one primitive explains.

    Both parts must stay below the limit separately: the sigma of the union alone
    hardly changes when a small fillet joins a large plane.
    """
    pairs = analysis.graph.pairs
    limit = tuning.merge_factor * analysis.noise
    slots: list[FitResult | None] = list(fits)
    count = len(slots)
    rejected: set[tuple[int, int]] = set()
    while count > 1:
        members = _members(labels, count)
        la, lb = labels[pairs[:, 0]], labels[pairs[:, 1]]
        mask = (la != lb) & (la >= 0) & (lb >= 0)
        low, high = np.minimum(la[mask], lb[mask]), np.maximum(la[mask], lb[mask])
        keys, shared = np.unique(low * count + high, return_counts=True)
        touched: set[int] = set()
        for key in keys[np.argsort(-shared)]:
            ra, rb = int(key // count), int(key % count)
            fit_a, fit_b = slots[ra], slots[rb]
            if ra in touched or rb in touched or (ra, rb) in rejected:
                continue
            if fit_a is None or fit_b is None:
                continue
            check()
            union = _explaining_union(analysis, members[ra], members[rb], fit_a, fit_b, limit, rng)
            if union is None:
                rejected.add((ra, rb))
                continue
            labels = np.where(labels == rb, ra, labels)
            slots[ra], slots[rb] = union, None
            touched.update((ra, rb))
            # the grown region may now merge with neighbours it was rejected by
            rejected = {pair for pair in rejected if ra not in pair}
        if not touched:
            break
    return _drop_empty(labels, slots)


def _explaining_union(
    analysis: MeshAnalysis,
    members_a: IntArray,
    members_b: IntArray,
    fit_a: FitResult,
    fit_b: FitResult,
    limit: float,
    rng: np.random.Generator,
) -> FitResult | None:
    """A fit (of either region's type) that explains both parts below `limit`, if any.

    When neither region's own primitive comes within `MERGE_PREFILTER` x the limit
    of the other region, no union fit is tried (torus fits cost 0.2 s each).
    """
    part_a = _sample(analysis, members_a, rng)
    part_b = _sample(analysis, members_b, rng)
    a_under_b = robust_sigma(signed_distance(fit_b.primitive, part_a[0]))
    b_under_a = robust_sigma(signed_distance(fit_a.primitive, part_b[0]))
    if min(a_under_b, b_under_a) > MERGE_PREFILTER * limit:
        return None
    points = np.vstack([part_a[0], part_b[0]])
    normals = np.vstack([part_a[1], part_b[1]])
    for kind in dict.fromkeys([fit_a.kind, fit_b.kind]):
        union = _try_fit(kind, points, normals, rng)
        if union is None:
            continue
        sigma_a = robust_sigma(signed_distance(union.primitive, part_a[0]))
        sigma_b = robust_sigma(signed_distance(union.primitive, part_b[0]))
        if max(sigma_a, sigma_b) < limit:
            return union
    return None


def _sample(
    analysis: MeshAnalysis, members: IntArray, rng: np.random.Generator
) -> tuple[FloatArray, FloatArray]:
    chosen = rng.choice(members, min(len(members), MERGE_SAMPLE), replace=False)
    vertices = analysis.mesh.faces[chosen, 0]
    return analysis.mesh.vertices[vertices], analysis.vertex_normals[vertices]


def _try_fit(
    kind: PrimitiveKind, points: FloatArray, normals: FloatArray, rng: np.random.Generator
) -> FitResult | None:
    try:
        return fit_primitive(kind, points, normals, rng)
    except FitError:
        return None


def _simplest_fits(
    analysis: MeshAnalysis,
    labels: IntArray,
    fits: list[FitResult],
    check: Checkpoint,
    rng: np.random.Generator,
) -> list[FitResult]:
    """Report each region as the simplest type that explains it.

    A plane region grown from a start patch that happened to favour a sphere keeps
    its faces, but is reported (and relaxed) as a plane.
    """
    result = []
    for fit, members in zip(fits, _members(labels, len(fits)), strict=True):
        check()
        region = np.zeros(analysis.face_count, dtype=bool)
        region[members] = True
        result.append(simplest_fit(analysis, region, fit, rng) if len(members) else fit)
    return result


def _drop_empty(
    labels: IntArray, slots: list[FitResult | None]
) -> tuple[IntArray, list[FitResult]]:
    keep = [index for index, fit in enumerate(slots) if fit is not None]
    remap = np.full(len(slots) + 1, -1, dtype=np.int64)
    remap[keep] = np.arange(len(keep))
    result = np.where(labels >= 0, remap[np.maximum(labels, 0)], -1)
    return result, [fit for fit in slots if fit is not None]


def _compact(labels: IntArray, fits: list[FitResult]) -> tuple[IntArray, list[FitResult]]:
    """Drop labels without faces; order regions by decreasing face count."""
    counts = np.bincount(labels[labels >= 0], minlength=len(fits))
    order = [int(i) for i in np.argsort(-counts, kind="stable") if counts[i] > 0]
    remap = np.full(len(fits) + 1, -1, dtype=np.int64)
    remap[order] = np.arange(len(order))
    result = np.where(labels >= 0, remap[np.maximum(labels, 0)], -1)
    return result, [fits[i] for i in order]


def _full_rms(
    mesh: EvalMesh, labels: IntArray, fits: list[FitResult], rng: np.random.Generator
) -> list[float]:
    """RMS distance of each region's vertices (at most 20 000) to its primitive."""
    result = []
    for fit, members in zip(fits, _members(labels, len(fits)), strict=True):
        vertices = np.unique(mesh.faces[members])
        if len(vertices) > 20_000:
            vertices = rng.choice(vertices, 20_000, replace=False)
        distance = signed_distance(fit.primitive, mesh.vertices[vertices])
        result.append(float(np.sqrt(np.mean(distance * distance))) if len(distance) else 0.0)
    return result
