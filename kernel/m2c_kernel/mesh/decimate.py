"""Mesh reduction with fast_simplification in a child process.

fast_simplification keeps its state in C++ globals, cannot be interrupted and may
print to stdout, which carries the protocol. It therefore runs in a spawned child
process. The child inherits the kernel's standard output, which already points at
stderr (`m2c_kernel.main`), and moves fd 1 to stderr once more before it imports
the library. The parent polls for the result and kills the child when the job is
cancelled, so a cancel takes effect within one polling interval.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import sys
import threading
from collections.abc import Callable, Iterator
from multiprocessing.connection import Connection

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.load import RawMesh, compact
from m2c_kernel.mesh.remap import nearest_centroid_map
from m2c_kernel.mesh.repair import MeshChange, remove_degenerate_faces, remove_duplicate_faces

AGGRESSIVENESS = 5.0
_POLL_S = 0.05

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
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(
        target=_child_main, args=(sender, vertices, faces, target_faces), daemon=True
    )
    with _stdin_detached():
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


_std_handle_lock = threading.Lock()


@contextlib.contextmanager
def _stdin_detached() -> Iterator[None]:
    """Start children with NUL as standard input (Windows).

    The kernel's reader thread keeps a synchronous read pending on the stdin pipe.
    A console child that receives a duplicate of that handle blocks in its startup
    (Python queries the handle) until the read completes, which can be forever.
    The process-wide standard input handle is therefore swapped for NUL while the
    child is created; the C runtime keeps its own handle for fd 0, so the reader
    thread is not affected.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    kernel32.SetStdHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
    std_input = ctypes.c_uint32(-10 & 0xFFFFFFFF)
    with _std_handle_lock, open(os.devnull, "rb") as null:
        previous = kernel32.GetStdHandle(std_input)
        kernel32.SetStdHandle(std_input, msvcrt.get_osfhandle(null.fileno()))
        try:
            yield
        finally:
            kernel32.SetStdHandle(std_input, previous)


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


def _centroids(mesh: RawMesh) -> npt.NDArray[np.float64]:
    centroids: npt.NDArray[np.float64] = mesh.vertices[mesh.faces].mean(axis=1)
    return centroids
