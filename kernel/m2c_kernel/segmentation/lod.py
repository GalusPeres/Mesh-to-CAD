"""Reduced copies of large scans for automatic segmentation, cached per scan.

Segmenting a 200 k-face copy and transferring the labels back is faster than
working on the full mesh and, because quadric decimation averages the noise,
slightly more accurate (`.work/research/algorithms-mesh.md` 2.6). The reduction
takes seconds, so the copy is kept per scan key in scan coordinates and only
transformed when the alignment changes.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.codes.regions import ProgressStage
from m2c_kernel.geometry import FloatArray, Matrix4, matrix_array, matrix_tuple, transform_points
from m2c_kernel.mesh.decimate import decimate
from m2c_kernel.mesh.load import RawMesh

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalMesh
    from m2c_kernel.segmentation.analysis import IntArray
    from m2c_kernel.session.jobs import JobContext

LOD_FACES = 200_000
REDUCE_ABOVE = 240_000
"""Meshes up to this size are segmented as they are."""
_CAPACITY = 2


@dataclass
class _Entry:
    scan_vertices: FloatArray
    """Vertices in scan coordinates."""
    faces: IntArray
    mesh: EvalMesh | None = None
    """The copy in the coordinates of the last request (keeps its analysis cached)."""
    source_key: str | None = None


class LevelOfDetailCache:
    """Reduced copies by scan key (least recently used first out)."""

    def __init__(self, capacity: int = _CAPACITY) -> None:
        self._capacity = capacity
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def get(
        self,
        mesh: EvalMesh,
        scan_key: str,
        matrix: Matrix4,
        job: JobContext,
    ) -> EvalMesh:
        """The reduced copy of `mesh` (the scan `scan_key` transformed by `matrix`).

        Returns `mesh` itself when it is small enough. Synthetic faces are left
        out of the copy: they must never influence a fit. The reduction runs in a
        child process that is killed when the job is cancelled.
        """
        if len(mesh.faces) <= REDUCE_ABOVE:
            return mesh
        with self._lock:
            entry = self._entries.get(scan_key)
            if entry is not None:
                self._entries.move_to_end(scan_key)
        if entry is None:
            job.progress(None, ProgressStage.REDUCING)
            entry = self._reduce(mesh, matrix, job)
            with self._lock:
                self._entries[scan_key] = entry
                while len(self._entries) > self._capacity:
                    self._entries.popitem(last=False)
        if entry.mesh is None or entry.source_key != mesh.key:
            # built with the class of `mesh`, so this module does not import the document layer
            vertices = transform_points(matrix, entry.scan_vertices)
            entry.mesh = type(mesh)(f"{mesh.key}:lod", vertices, entry.faces, None)
            entry.source_key = mesh.key
        return entry.mesh

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @staticmethod
    def _reduce(mesh: EvalMesh, matrix: Matrix4, job: JobContext) -> _Entry:
        usable = RawMesh(mesh.vertices, mesh.faces[~mesh.synthetic])
        reduced = decimate(usable, LOD_FACES, job.check_cancelled).mesh
        to_scan = matrix_tuple(np.linalg.inv(matrix_array(matrix)))
        return _Entry(transform_points(to_scan, reduced.vertices), reduced.faces)


LEVELS_OF_DETAIL = LevelOfDetailCache()
"""The process-wide cache used by the segmentation command."""
