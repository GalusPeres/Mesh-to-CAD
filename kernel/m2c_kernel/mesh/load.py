"""Reading mesh files and welding triangle soup.

Binary STL is read straight into float32 with `np.fromfile`, so a 2M-face soup
never exists as float64. ASCII STL and plain triangle OBJ files are parsed with
numpy block by block; PLY and unusual OBJ files (polygons, negative indices) go
through trimesh without processing. Measurements: `.work/research/algorithms-mesh.md` 1.1.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.mesh import ErrorCode
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import MAX_IMPORT_BYTES, MAX_IMPORT_FACES
from m2c_kernel.protocol.errors import KernelError

SUPPORTED_SUFFIXES = (".stl", ".obj", ".ply")

WELD_GRID_BITS = 20
"""The weld grid divides the largest extent into 2^20 cells (about 0.1 µm per 100 mm).

The cell follows the size of the part rather than a fixed length, so welding works
the same whatever unit the file uses, and three cell indices always pack into one
int64 key.
"""

_BLOCK_BYTES = 32 << 20
_STL_RECORD = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
_STL_HEADER_BYTES = 84
_ASCII_VERTEX = re.compile(rb"vertex\s+(\S+\s+\S+\s+\S+)", re.IGNORECASE)
_OBJ_INDEX_SUFFIX = re.compile(rb"/\S*")

type IndexArray = npt.NDArray[np.int64]
type Coordinates = npt.NDArray[np.float32] | FloatArray


@dataclass(frozen=True)
class RawMesh:
    """Vertices (float64) and triangles (int64 vertex indices)."""

    vertices: FloatArray
    faces: IndexArray


@dataclass(frozen=True)
class MeshFile:
    """The content of a mesh file before welding.

    STL files are triangle soup: face k uses vertices 3k, 3k+1 and 3k+2, which
    stay float32 as stored. Faces with a non-finite corner are dropped and counted.
    """

    vertices: Coordinates
    faces: IndexArray
    dropped_faces: int = 0


@dataclass(frozen=True)
class PendingImport:
    """A loaded file waiting for the user to confirm unit and reduction (`mesh.commitImport`).

    `noise` holds the noise estimate per unit, measured at that unit's scale.
    """

    id: str
    file_name: str
    sha256: str
    mesh: RawMesh
    counts: dict[str, int]
    noise: dict[str, float | None]


def read_mesh(path: Path) -> MeshFile:
    """Read an STL, OBJ or PLY file without repairing anything."""
    if not path.is_file():
        raise KernelError(ErrorCode.FILE_NOT_FOUND, {"fileName": path.name})
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise KernelError(ErrorCode.FILE_TOO_LARGE, {"bytes": size, "maxBytes": MAX_IMPORT_BYTES})
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise KernelError(ErrorCode.UNSUPPORTED_FORMAT, {"suffix": suffix})

    try:
        if suffix == ".stl":
            vertices, faces = _read_stl(path, size)
        else:
            loaded = _read_plain_obj(path) if suffix == ".obj" else None
            vertices, faces = loaded if loaded is not None else _read_with_trimesh(path)
    except (KernelError, MemoryError):
        raise
    except Exception as error:
        raise KernelError(
            ErrorCode.READ_FAILED, {"fileName": path.name}, details=repr(error)
        ) from error

    if len(faces) > MAX_IMPORT_FACES:
        raise KernelError(
            ErrorCode.TOO_MANY_FACES, {"faces": len(faces), "maxFaces": MAX_IMPORT_FACES}
        )
    if len(faces) and (faces.min() < 0 or faces.max() >= len(vertices)):
        raise KernelError(
            ErrorCode.READ_FAILED, {"fileName": path.name}, details="face index out of range"
        )
    mesh = _without_non_finite_faces(vertices, faces)
    if len(mesh.faces) == 0:
        raise KernelError(ErrorCode.EMPTY, {"fileName": path.name})
    return mesh


def weld_vertices(mesh: RawMesh | MeshFile) -> tuple[RawMesh, int]:
    """Merge vertices that fall into the same cell of the weld grid (`WELD_GRID_BITS`).

    Bit-identical duplicates, as in STL triangle soup, always merge. Two distinct
    points closer than one cell may still land in neighbouring cells; that does not
    matter because welding only has to restore the connectivity of the soup.
    Returns the welded mesh and the number of merged vertices.
    """
    vertices = mesh.vertices
    low = vertices.min(axis=0).astype(np.float64)
    extent = float((vertices.max(axis=0).astype(np.float64) - low).max())
    cell = max(extent, 1e-12) / float(1 << WELD_GRID_BITS)
    key = np.zeros(len(vertices), dtype=np.int64)
    for axis in range(3):
        column = np.floor((vertices[:, axis].astype(np.float64) - low[axis]) / cell)
        key = (key << (WELD_GRID_BITS + 1)) | column.astype(np.int64)
    _, first, inverse = np.unique(key, return_index=True, return_inverse=True)
    # Keep the vertex order of the input (first occurrence wins), so that welding a
    # mesh without duplicates returns it unchanged.
    order = np.argsort(first, kind="stable")
    rank = np.empty(len(first), dtype=np.int32)
    rank[order] = np.arange(len(first), dtype=np.int32)
    index = rank[inverse.reshape(-1)]
    welded = RawMesh(
        vertices[first[order]].astype(np.float64), index[mesh.faces].astype(np.int64, copy=False)
    )
    return welded, len(vertices) - len(first)


def compact(mesh: RawMesh) -> RawMesh:
    """Remove unreferenced vertices and renumber the faces; faces keep their order."""
    used = np.zeros(len(mesh.vertices), dtype=bool)
    used[mesh.faces.ravel()] = True
    new_index = np.cumsum(used) - 1
    return RawMesh(mesh.vertices[used], new_index[mesh.faces].astype(np.int64))


def _read_stl(path: Path, size: int) -> tuple[Coordinates, IndexArray]:
    """Binary STL when the header's triangle count matches the size, else ASCII."""
    with path.open("rb") as handle:
        head = handle.read(max(_STL_HEADER_BYTES, 512))
    count = (
        int(np.frombuffer(head[80:84], dtype="<u4")[0]) if len(head) >= _STL_HEADER_BYTES else -1
    )
    binary_size = _STL_HEADER_BYTES + count * _STL_RECORD.itemsize
    looks_ascii = head.lstrip()[:5].lower() == b"solid" and b"facet" in head.lower()
    if count >= 0 and (size == binary_size or (size > binary_size and not looks_ascii)):
        return _read_binary_stl(path, count)
    if looks_ascii or head.lstrip()[:5].lower() == b"solid":
        return _read_ascii_stl(path)
    raise KernelError(
        ErrorCode.INVALID_STL,
        {"fileName": path.name},
        details=f"header count {count} needs {binary_size} bytes, file has {size}",
    )


def _read_binary_stl(path: Path, count: int) -> tuple[Coordinates, IndexArray]:
    if count > MAX_IMPORT_FACES:
        raise KernelError(ErrorCode.TOO_MANY_FACES, {"faces": count, "maxFaces": MAX_IMPORT_FACES})
    with path.open("rb") as handle:
        handle.seek(_STL_HEADER_BYTES)
        records = np.fromfile(handle, dtype=_STL_RECORD, count=count)
    vertices = np.ascontiguousarray(records["corners"]).reshape(-1, 3)
    return vertices, np.arange(3 * count, dtype=np.int64).reshape(-1, 3)


def _read_ascii_stl(path: Path) -> tuple[Coordinates, IndexArray]:
    parts = [
        np.array(b" ".join(_ASCII_VERTEX.findall(block)).split(), dtype=np.float32)
        for block in _line_blocks(path)
    ]
    coordinates = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    if len(coordinates) % 9:
        raise KernelError(
            ErrorCode.INVALID_STL, {"fileName": path.name}, details="incomplete facet"
        )
    count = len(coordinates) // 9
    return coordinates.reshape(-1, 3), np.arange(3 * count, dtype=np.int64).reshape(-1, 3)


def _read_plain_obj(path: Path) -> tuple[FloatArray, IndexArray] | None:
    """Numpy fast path for OBJ files with plain triangles; None for anything else."""
    vertex_parts: list[FloatArray] = []
    face_parts: list[IndexArray] = []
    for block in _line_blocks(path):
        lines = block.split(b"\n")
        vertex_lines = [line[2:] for line in lines if line[:2] == b"v "]
        face_lines = [line[2:] for line in lines if line[:2] == b"f "]
        if face_lines:
            joined = b" ".join(face_lines)
            if b"-" in joined:
                return None
            if b"/" in joined:
                joined = _OBJ_INDEX_SUFFIX.sub(b"", joined)
            indices = np.array(joined.split(), dtype=np.int64)
            if len(indices) != 3 * len(face_lines):
                return None
            face_parts.append(indices)
        if vertex_lines:
            coordinates = np.array(b" ".join(vertex_lines).split(), dtype=np.float64)
            if len(coordinates) != 3 * len(vertex_lines):
                # Vertex colours ("v x y z r g b") add values per line.
                rows = [line.split()[:3] for line in vertex_lines]
                if any(len(row) != 3 for row in rows):
                    return None
                coordinates = np.array(rows, dtype=np.float64).ravel()
            vertex_parts.append(coordinates)
    if not face_parts or not vertex_parts:
        return None
    vertices = np.concatenate(vertex_parts).reshape(-1, 3)
    faces = np.concatenate(face_parts).reshape(-1, 3) - 1
    return vertices, faces


def _read_with_trimesh(path: Path) -> tuple[FloatArray, IndexArray]:
    import trimesh

    mesh = trimesh.load(str(path), force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise KernelError(ErrorCode.EMPTY, {"fileName": path.name})
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64)


def _line_blocks(path: Path) -> Iterator[bytes]:
    """The file in blocks of whole lines, so large text files are parsed piecewise."""
    rest = b""
    with path.open("rb") as handle:
        while chunk := handle.read(_BLOCK_BYTES):
            data = rest + chunk
            cut = data.rfind(b"\n") + 1
            if cut == 0:
                rest = data
                continue
            rest = data[cut:]
            yield data[:cut]
    if rest:
        yield rest


def _without_non_finite_faces(vertices: Coordinates, faces: IndexArray) -> MeshFile:
    finite_vertex = np.isfinite(vertices).all(axis=1)
    if finite_vertex.all():
        return MeshFile(vertices, faces)
    keep = finite_vertex[faces].all(axis=1)
    kept = faces[keep]
    used = np.zeros(len(vertices), dtype=bool)
    used[kept.ravel()] = True
    new_index = np.cumsum(used) - 1
    return MeshFile(vertices[used], new_index[kept], int((~keep).sum()))
