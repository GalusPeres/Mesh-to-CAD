"""Mesh reduction with fast_simplification in a child process.

fast_simplification is not thread-safe, cannot be interrupted and may print to
stdout, which carries the protocol. It therefore runs in a spawned child whose
stdout is moved to stderr before anything is imported; the parent polls for the
result and kills the child when the job is cancelled.
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable
from multiprocessing.connection import Connection

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.load import RawMesh
from m2c_kernel.mesh.remap import nearest_centroid_map
from m2c_kernel.mesh.repair import MeshChange

AGGRESSIVENESS = 5.0
_POLL_S = 0.05

type Arrays = tuple[npt.NDArray[np.float32], npt.NDArray[np.int32]]


class DecimationError(Exception):
    """The child process ended without a result."""


def decimate(
    mesh: RawMesh, target_faces: int, check_cancelled: Callable[[], None] = lambda: None
) -> MeshChange:
    """Reduce to at most `target_faces` faces; the face map is by nearest centroid."""
    if target_faces >= len(mesh.faces):
        n = len(mesh.faces)
        return MeshChange(mesh, np.arange(n, dtype=np.int64), np.zeros(n, dtype=bool))
    vertices, faces = _run_in_child(
        mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32), target_faces, check_cancelled
    )
    reduced = _compact(RawMesh(vertices.astype(np.float64), faces.astype(np.int64)))
    new_to_old = nearest_centroid_map(_centroids(mesh), _centroids(reduced))
    counts = {"facesBefore": len(mesh.faces), "facesAfter": len(reduced.faces)}
    return MeshChange(reduced, new_to_old, np.zeros(len(reduced.faces), dtype=bool), counts)


def _run_in_child(
    vertices: npt.NDArray[np.float32],
    faces: npt.NDArray[np.int32],
    target_faces: int,
    check_cancelled: Callable[[], None],
) -> Arrays:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(
        target=_child_main, args=(sender, vertices, faces, target_faces), daemon=True
    )
    child.start()
    sender.close()
    try:
        while not receiver.poll(_POLL_S):
            try:
                check_cancelled()
            except BaseException:
                child.kill()
                raise
            if not child.is_alive() and not receiver.poll(0):
                raise DecimationError(f"exit code {child.exitcode}")
        try:
            result: Arrays | str = receiver.recv()
        except EOFError as error:
            raise DecimationError(f"exit code {child.exitcode}") from error
    finally:
        child.join(timeout=5)
        if child.is_alive():
            child.kill()
        receiver.close()
    if isinstance(result, str):
        raise DecimationError(result)
    return result


def _child_main(
    sender: Connection,
    vertices: npt.NDArray[np.float32],
    faces: npt.NDArray[np.int32],
    target_faces: int,
) -> None:
    os.dup2(2, 1)
    try:
        import fast_simplification

        out_vertices, out_faces = fast_simplification.simplify(
            vertices, faces, target_count=int(target_faces), agg=AGGRESSIVENESS
        )
        sender.send((np.asarray(out_vertices, np.float32), np.asarray(out_faces, np.int32)))
    except Exception as error:
        sender.send(repr(error))
    finally:
        sender.close()


def _compact(mesh: RawMesh) -> RawMesh:
    used = np.zeros(len(mesh.vertices), dtype=bool)
    used[mesh.faces.ravel()] = True
    new_index = np.cumsum(used) - 1
    return RawMesh(mesh.vertices[used], new_index[mesh.faces].astype(np.int64))


def _centroids(mesh: RawMesh) -> npt.NDArray[np.float64]:
    centroids: npt.NDArray[np.float64] = mesh.vertices[mesh.faces].mean(axis=1)
    return centroids
