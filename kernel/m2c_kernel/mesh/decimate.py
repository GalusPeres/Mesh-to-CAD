"""Mesh reduction with fast_simplification in a child process.

fast_simplification keeps its state in C++ globals, cannot be interrupted and may
print to stdout, which carries the protocol. It therefore runs in a spawned child
process (`mesh/child.py`) that is killed when the job is cancelled.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.child import ChildCallError, run_in_child
from m2c_kernel.mesh.load import RawMesh, compact
from m2c_kernel.mesh.remap import nearest_centroid_map
from m2c_kernel.mesh.repair import MeshChange, remove_degenerate_faces, remove_duplicate_faces

AGGRESSIVENESS = 5.0

type Arrays = tuple[npt.NDArray[np.float32], npt.NDArray[np.int32]]


class DecimationError(Exception):
    """The child process ended without a result."""


def decimate(
    mesh: RawMesh, target_faces: int, check_cancelled: Callable[[], None] = lambda: None
) -> MeshChange:
    """Reduce to at most `target_faces` faces.

    Quadric decimation merges faces, so there is no exact face map: every new face
    maps to the old face with the nearest centroid. Degenerate and duplicate faces
    that the collapse can leave behind are removed as part of the step.
    """
    if target_faces >= len(mesh.faces):
        return MeshChange.identity(
            mesh, {"facesBefore": len(mesh.faces), "facesAfter": len(mesh.faces)}
        )
    vertices, faces = _run_in_child(
        mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32), target_faces, check_cancelled
    )
    reduced = RawMesh(vertices.astype(np.float64), faces.astype(np.int64))
    cleaned = remove_degenerate_faces(reduced)
    cleaned = cleaned.then(remove_duplicate_faces(cleaned.mesh))
    result = compact(cleaned.mesh)
    new_to_old = nearest_centroid_map(_centroids(mesh), _centroids(result))
    counts = {"facesBefore": len(mesh.faces), "facesAfter": len(result.faces)}
    return MeshChange(result, new_to_old, np.zeros(len(result.faces), dtype=bool), counts)


def _run_in_child(
    vertices: npt.NDArray[np.float32],
    faces: npt.NDArray[np.int32],
    target_faces: int,
    check_cancelled: Callable[[], None],
) -> Arrays:
    try:
        return run_in_child(_simplify, (vertices, faces, target_faces), check_cancelled)
    except ChildCallError as error:
        raise DecimationError(str(error)) from error


def _simplify(
    vertices: npt.NDArray[np.float32], faces: npt.NDArray[np.int32], target_faces: int
) -> Arrays:
    """Runs in the child process."""
    import fast_simplification

    out_vertices, out_faces = fast_simplification.simplify(
        vertices, faces, target_count=int(target_faces), agg=AGGRESSIVENESS
    )
    return np.asarray(out_vertices, np.float32), np.asarray(out_faces, np.int32)


def _centroids(mesh: RawMesh) -> npt.NDArray[np.float64]:
    centroids: npt.NDArray[np.float64] = mesh.vertices[mesh.faces].mean(axis=1)
    return centroids
