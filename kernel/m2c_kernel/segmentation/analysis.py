"""Per-mesh data shared by region growing and segmentation (computed once per mesh).

Face normals come from the jet fit (accurate to 1-3 degrees on noisy scans), the
crease zone from the jet residual: a local quadric cannot follow a crease, so the
residual rises well above the noise within the fit radius of one
(`.work/research/algorithms-mesh.md` 2.4).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

import numpy as np
import numpy.typing as npt
import scipy.sparse as sp
from scipy.spatial import cKDTree

from m2c_kernel.geometry import FloatArray
from m2c_kernel.mesh.normals import voxel_subsample

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.mesh.topology import FaceGraph

type BoolArray = npt.NDArray[np.bool_]
type IntArray = npt.NDArray[np.int64]

CREASE_FACTOR = 3.0
"""A vertex is in a crease zone when its 1-ring mean residual exceeds this x the median."""
CREASE_MIN_AREA = 0.5
"""Crease-zone fragments below this area (mm^2) are noise."""
MIN_NOISE = 1e-3
"""Lower bound of the noise estimate (mm), for noise-free synthetic meshes."""
CURVATURE_RADIUS_MM = 1.0
"""Curvatures are averaged over this radius before faces are compared."""
_CURVATURE_CELL_MM = 0.5
_CURVATURE_NEIGHBOURS = 32
"""Upper bound of samples within the radius (about 13 on a surface with 0.5 mm cells)."""


@dataclass
class MeshAnalysis:
    """Jet normals, curvature and crease zone of one mesh, by face."""

    mesh: EvalMesh

    @property
    def face_count(self) -> int:
        return len(self.mesh.faces)

    @property
    def graph(self) -> FaceGraph:
        return self.mesh.face_graph

    @cached_property
    def noise(self) -> float:
        return max(self.mesh.jet.noise, MIN_NOISE)

    @cached_property
    def vertex_normals(self) -> FloatArray:
        return self.mesh.jet.normals

    @cached_property
    def face_normals(self) -> FloatArray:
        summed = self.vertex_normals[self.mesh.faces].sum(axis=1)
        normals: FloatArray = summed / np.maximum(np.linalg.norm(summed, axis=1), 1e-300)[:, None]
        return normals

    @cached_property
    def dominant_curvature(self) -> FloatArray:
        """Per face: the principal curvature with the larger magnitude, averaged over 1 mm.

        Jet curvatures of a noisy scan scatter by about 0.035 / mm from vertex to
        vertex, as much as the curvature of an R30 cylinder. Averaging over a fixed
        spatial radius (not a number of rings, which depends on the triangle size)
        halves the scatter, so curvature-homogeneous patches stay connected.
        """
        jet, vertices = self.mesh.jet, self.mesh.vertices
        per_vertex = np.where(np.abs(jet.k1) >= np.abs(jet.k2), jet.k1, jet.k2)
        sample = voxel_subsample(vertices, _CURVATURE_CELL_MM)
        points = vertices[sample]
        tree = cKDTree(points)
        k = min(_CURVATURE_NEIGHBOURS, len(points))
        distance, neighbour = tree.query(
            points, k=k, distance_upper_bound=CURVATURE_RADIUS_MM, workers=-1
        )
        found = np.isfinite(distance.reshape(len(points), k))
        neighbour = np.minimum(neighbour.reshape(len(points), k), len(points) - 1)
        values = np.where(found, per_vertex[sample][neighbour], 0.0)
        averaged = values.sum(axis=1) / found.sum(axis=1)
        _, nearest = tree.query(vertices, workers=-1)
        result: FloatArray = averaged[nearest][self.mesh.faces].mean(axis=1)
        return result

    @cached_property
    def crease(self) -> BoolArray:
        faces = self.mesh.faces
        residual = self.mesh.jet.residual
        score = _vertex_ring_mean(faces, len(self.mesh.vertices)) @ (
            residual / max(float(np.median(residual)), 1e-12)
        )
        zone: BoolArray = (score > CREASE_FACTOR)[faces].any(axis=1)
        zone &= ~self.mesh.synthetic
        if not zone.any():
            return zone
        labels = self.graph.components(zone)
        area = self.mesh.face_areas
        component_area = np.bincount(labels[zone], weights=area[zone])
        keep = np.zeros(self.face_count, dtype=bool)
        keep[zone] = component_area[labels[zone]] >= CREASE_MIN_AREA
        return keep

    @cached_property
    def centroid_tree(self) -> cKDTree:
        return cKDTree(self.mesh.face_centroids)

    @cached_property
    def usable(self) -> BoolArray:
        """Faces that may seed or join a fit (synthetic hole-filling faces never do)."""
        result: BoolArray = ~self.mesh.synthetic
        return result

    def warm_up(self, check: Callable[[], None] = lambda: None) -> None:
        """Compute everything region growing needs, calling `check` between the steps."""
        for step in ("face_normals", "dominant_curvature", "crease", "centroid_tree"):
            check()
            getattr(self, step)
        check()


def _vertex_ring_mean(faces: IntArray, vertex_count: int) -> sp.csr_matrix:
    """Row-normalised vertex adjacency (mean over the 1-ring including the vertex)."""
    a = faces[:, [0, 1, 2]].ravel()
    b = faces[:, [1, 2, 0]].ravel()
    rows = np.r_[a, b, np.arange(vertex_count)]
    cols = np.r_[b, a, np.arange(vertex_count)]
    matrix = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(vertex_count, vertex_count))
    matrix.sum_duplicates()  # duplicate edges count once
    matrix.data[:] = 1.0
    degree = np.asarray(matrix.sum(axis=1)).ravel()
    return sp.diags(1.0 / np.maximum(degree, 1.0)) @ matrix


_CACHE: WeakKeyDictionary[EvalMesh, MeshAnalysis] = WeakKeyDictionary()
_LOCK = threading.Lock()


def analyse(mesh: EvalMesh) -> MeshAnalysis:
    """The analysis of a mesh, kept as long as the mesh object lives."""
    with _LOCK:
        analysis = _CACHE.get(mesh)
        if analysis is None:
            analysis = MeshAnalysis(mesh)
            _CACHE[mesh] = analysis
        return analysis


def is_analysed(mesh: EvalMesh) -> bool:
    """True when the expensive per-mesh data already exists (no progress bar needed)."""
    with _LOCK:
        analysis = _CACHE.get(mesh)
    return analysis is not None and "centroid_tree" in analysis.__dict__
