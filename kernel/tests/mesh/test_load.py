"""Reading STL, OBJ and PLY files and welding their vertices."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import trimesh

from m2c_kernel.mesh.load import RawMesh, compact, read_mesh, weld_vertices
from m2c_kernel.mesh.topology import edge_topology
from m2c_kernel.protocol.errors import KernelError
from tests.synthetic import sphere_scan, write_binary_stl

type FloatArray = npt.NDArray[np.float64]


@pytest.fixture(scope="module")
def sphere() -> tuple[FloatArray, np.ndarray]:
    return sphere_scan(radius=20.0, subdivisions=3, sigma=0.02)


def _soup(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Triangle corner coordinates in a canonical order, independent of vertex numbering."""
    corners = np.asarray(vertices, dtype=np.float64)[faces].reshape(len(faces), 9)
    return corners[np.lexsort(corners.T[::-1])]


def _trimesh_soup(path: Path) -> np.ndarray:
    mesh = trimesh.load(str(path), force="mesh", process=False)
    return _soup(mesh.vertices, mesh.faces)


def test_binary_stl_is_read_as_float32_soup_equal_to_trimesh(
    tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]
) -> None:
    path = write_binary_stl(tmp_path / "part.stl", *sphere)
    loaded = read_mesh(path)
    assert loaded.vertices.dtype == np.float32
    assert len(loaded.vertices) == 3 * len(sphere[1])
    reference = trimesh.load(str(path), force="mesh", process=False)
    np.testing.assert_array_equal(loaded.vertices, reference.vertices)
    np.testing.assert_array_equal(loaded.faces, reference.faces)


def test_binary_stl_whose_header_starts_with_solid_is_still_binary(
    tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]
) -> None:
    path = write_binary_stl(tmp_path / "part.stl", *sphere)
    data = bytearray(path.read_bytes())
    data[:20] = b"solid exported part ".ljust(20)
    path.write_bytes(bytes(data))
    assert len(read_mesh(path).faces) == len(sphere[1])


def test_ascii_stl_equals_trimesh(tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]) -> None:
    vertices, faces = sphere
    path = tmp_path / "part.stl"
    trimesh.Trimesh(vertices, faces, process=False).export(str(path), file_type="stl_ascii")
    loaded = read_mesh(path)
    np.testing.assert_allclose(
        _soup(loaded.vertices, loaded.faces), _trimesh_soup(path), rtol=0, atol=1e-5
    )


def test_truncated_binary_stl_is_reported(
    tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]
) -> None:
    path = write_binary_stl(tmp_path / "part.stl", *sphere)
    path.write_bytes(path.read_bytes()[:-30])
    with pytest.raises(KernelError) as caught:
        read_mesh(path)
    assert caught.value.code == "mesh.invalidStl"
    assert caught.value.params == {"fileName": "part.stl"}


def _write_obj(path: Path, vertices: FloatArray, faces: np.ndarray, style: str) -> Path:
    lines = []
    for x, y, z in vertices:
        colour = " 0.5 0.5 0.5" if style == "colours" else ""
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}{colour}")
    if style == "slashes":
        lines += ["vt 0 0", "vn 0 0 1"]
    lines.append("g part")
    for a, b, c in faces + 1:
        if style == "slashes":
            lines.append(f"f {a}/1/1 {b}/1/1 {c}/1/1")
        else:
            lines.append(f"f {a} {b} {c}")
    path.write_text("\r\n".join(lines) + "\r\n")
    return path


@pytest.mark.parametrize("style", ["plain", "slashes", "colours"])
def test_obj_fast_path_equals_trimesh(
    tmp_path: Path, sphere: tuple[FloatArray, np.ndarray], style: str
) -> None:
    path = _write_obj(tmp_path / "part.obj", *sphere, style=style)
    loaded = read_mesh(path)
    assert len(loaded.faces) == len(sphere[1])
    np.testing.assert_allclose(
        _soup(loaded.vertices, loaded.faces), _trimesh_soup(path), rtol=0, atol=1e-12
    )


def test_obj_with_quads_falls_back_to_trimesh(tmp_path: Path) -> None:
    path = tmp_path / "quad.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    loaded = read_mesh(path)
    assert len(loaded.faces) == 2
    assert np.isclose(np.ptp(np.asarray(loaded.vertices), axis=0), [1.0, 1.0, 0.0]).all()


def test_ply_is_read(tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]) -> None:
    path = tmp_path / "part.ply"
    trimesh.Trimesh(*sphere, process=False).export(str(path))
    loaded = read_mesh(path)
    np.testing.assert_allclose(_soup(loaded.vertices, loaded.faces), _soup(*sphere), atol=1e-6)


def test_faces_with_non_finite_corners_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "part.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv nan 0 1\nf 1 2 3\nf 1 2 4\nf 2 3 4\n")
    loaded = read_mesh(path)
    assert loaded.dropped_faces == 2
    assert loaded.faces.tolist() == [[0, 1, 2]]
    assert np.isfinite(loaded.vertices).all()


def test_empty_and_broken_files_are_reported(tmp_path: Path) -> None:
    empty = tmp_path / "empty.obj"
    empty.write_text("# nothing\n")
    with pytest.raises(KernelError) as caught:
        read_mesh(empty)
    assert caught.value.code in {"mesh.empty", "mesh.readFailed"}
    out_of_range = tmp_path / "broken.obj"
    out_of_range.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n")
    with pytest.raises(KernelError) as broken:
        read_mesh(out_of_range)
    assert broken.value.code == "mesh.readFailed"


def test_welding_is_independent_of_the_unit(
    tmp_path: Path, sphere: tuple[FloatArray, np.ndarray]
) -> None:
    vertices, faces = sphere
    for scale in (1.0, 0.001, 25.4):
        loaded = read_mesh(write_binary_stl(tmp_path / f"s{scale}.stl", vertices * scale, faces))
        welded, merged = weld_vertices(loaded)
        assert len(welded.vertices) == len(vertices)
        assert merged == 3 * len(faces) - len(vertices)
        topology = edge_topology(welded.faces)
        assert (topology.valence == 2).all()


def test_welding_keeps_the_vertex_order() -> None:
    vertices, faces = sphere_scan(subdivisions=2)
    welded, merged = weld_vertices(RawMesh(vertices, faces))
    assert merged == 0
    np.testing.assert_array_equal(welded.vertices, vertices)
    np.testing.assert_array_equal(welded.faces, faces)


def test_compact_removes_unused_vertices() -> None:
    mesh = RawMesh(np.arange(15, dtype=float).reshape(5, 3), np.array([[0, 2, 4]]))
    compacted = compact(mesh)
    assert compacted.faces.tolist() == [[0, 1, 2]]
    assert compacted.vertices[:, 0].tolist() == [0.0, 6.0, 12.0]
