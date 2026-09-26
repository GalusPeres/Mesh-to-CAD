"""Reading mesh files and welding triangle soup.

Binary STL is read straight into float32 with `np.fromfile` (a 2M-face soup
never exists as float64); plain triangle OBJ files take a numpy fast path; ASCII
STL, PLY and unusual OBJ files go through trimesh without processing.
Measurements: `.work/research/algorithms-mesh.md` 1.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.mesh import ErrorCode
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import MAX_IMPORT_BYTES, MAX_IMPORT_FACES
from m2c_kernel.mesh.topology import pack_rows
from m2c_kernel.protocol.errors import KernelError

SUPPORTED_SUFFIXES = (".stl", ".obj", ".ply")
WELD_TOLERANCE_MM = 1e-4


@dataclass(frozen=True)
class RawMesh:
    vertices: FloatArray
    faces: npt.NDArray[np.int64]


@dataclass(frozen=True)
class PendingImport:
    """A loaded file waiting for the user to confirm unit and reduction (`mesh.commitImport`)."""

    id: str
    file_name: str
    sha256: str
    mesh: RawMesh
    merged_vertices: int


def read_mesh(path: Path) -> RawMesh:
    """Read an STL, OBJ or PLY file without any processing."""
    if not path.is_file():
        raise KernelError(ErrorCode.FILE_NOT_FOUND, {"fileName": path.name})
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise KernelError(ErrorCode.FILE_TOO_LARGE, {"bytes": size, "maxBytes": MAX_IMPORT_BYTES})
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise KernelError(ErrorCode.UNSUPPORTED_FORMAT, {"suffix": suffix})

    try:
        loaded = _read_binary_stl(path, size) if suffix == ".stl" else None
        if loaded is None and suffix == ".obj":
            loaded = _read_plain_obj(path)
        if loaded is None:
            loaded = _read_with_trimesh(path)
    except KernelError:
        raise
    except Exception as error:
        raise KernelError(
            ErrorCode.READ_FAILED, {"fileName": path.name}, details=repr(error)
        ) from error
    vertices, faces = loaded
    if len(faces) == 0 or len(vertices) == 0:
        raise KernelError(ErrorCode.EMPTY, {"fileName": path.name})
    if len(faces) > MAX_IMPORT_FACES:
        raise KernelError(
            ErrorCode.TOO_MANY_FACES, {"faces": len(faces), "maxFaces": MAX_IMPORT_FACES}
        )
    if not np.isfinite(vertices).all():
        raise KernelError(
            ErrorCode.READ_FAILED, {"fileName": path.name}, details="non-finite vertices"
        )
    return RawMesh(vertices, faces)


_STL_RECORD = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])


def _read_binary_stl(path: Path, size: int) -> tuple[FloatArray, npt.NDArray[np.int64]] | None:
    """Triangle soup of a binary STL, or None if the file is ASCII."""
    if size < 84:
        return None
    with path.open("rb") as handle:
        handle.seek(80)
        count = int(np.frombuffer(handle.read(4), dtype="<u4")[0])
        if 84 + count * _STL_RECORD.itemsize != size:
            return None
        if count > MAX_IMPORT_FACES:
            raise KernelError(
                ErrorCode.TOO_MANY_FACES, {"faces": count, "maxFaces": MAX_IMPORT_FACES}
            )
        records = np.fromfile(handle, dtype=_STL_RECORD, count=count)
    vertices = np.ascontiguousarray(records["corners"]).reshape(-1, 3)
    faces = np.arange(3 * count, dtype=np.int64).reshape(-1, 3)
    return vertices, faces


def _read_plain_obj(path: Path) -> tuple[FloatArray, npt.NDArray[np.int64]] | None:
    """Numpy fast path for OBJ files with plain triangles; None for anything else."""
    import re

    lines = path.read_bytes().splitlines()
    vertex_lines = [line[2:] for line in lines if line[:2] == b"v "]
    face_lines = [line[2:] for line in lines if line[:2] == b"f "]
    joined = b" ".join(face_lines)
    if b"-" in joined:
        return None
    if b"/" in joined:
        joined = re.sub(rb"/\S*", b"", joined)
    indices = np.array(joined.split(), dtype=np.int64)
    if len(indices) != 3 * len(face_lines):
        return None
    coordinates = np.array(b" ".join(vertex_lines).split(), dtype=np.float64)
    if len(coordinates) != 3 * len(vertex_lines):
        coordinates = np.array([line.split()[:3] for line in vertex_lines], dtype=np.float64)
    return coordinates.reshape(-1, 3), indices.reshape(-1, 3) - 1


def _read_with_trimesh(path: Path) -> tuple[FloatArray, npt.NDArray[np.int64]]:
    import trimesh

    mesh = trimesh.load(str(path), force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise KernelError(ErrorCode.EMPTY, {"fileName": path.name})
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64)


def weld_vertices(mesh: RawMesh, tolerance: float = WELD_TOLERANCE_MM) -> tuple[RawMesh, int]:
    """Merge duplicate vertices by snapping to a grid of cell size `tolerance`.

    This welds the bit-identical duplicates of STL triangle soup; two points
    closer than `tolerance` can still fall into neighbouring cells. Returns the
    welded mesh and the number of merged vertices.
    """
    low = mesh.vertices.min(axis=0)
    key = pack_rows(np.floor((mesh.vertices - low) / tolerance).astype(np.int64))
    _, first, inverse = np.unique(key, return_index=True, return_inverse=True)
    index = inverse.reshape(-1).astype(np.int32)
    welded = RawMesh(mesh.vertices[first].astype(np.float64), index[mesh.faces].astype(np.int64))
    return welded, len(mesh.vertices) - len(first)


def compact(mesh: RawMesh) -> RawMesh:
    """Remove unreferenced vertices and renumber the faces."""
    used = np.zeros(len(mesh.vertices), dtype=bool)
    used[mesh.faces.ravel()] = True
    new_index = np.cumsum(used) - 1
    return RawMesh(mesh.vertices[used], new_index[mesh.faces])
