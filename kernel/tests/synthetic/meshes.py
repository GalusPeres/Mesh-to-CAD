"""Triangulated test surfaces with known parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from tests.synthetic.noise import add_scanner_noise

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class Patch:
    """A surface patch: vertices, faces, exact vertex normals and the true primitive."""

    vertices: FloatArray
    faces: IntArray
    normals: FloatArray
    primitive: Primitive


def _grid_faces(nu: int, nv: int) -> IntArray:
    u0, v0 = np.meshgrid(np.arange(nu - 1), np.arange(nv - 1), indexing="ij")
    a = u0 * nv + v0
    b = (u0 + 1) * nv + v0
    c = b + 1
    d = a + 1
    faces = np.concatenate(
        [np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)]
    )
    return faces.astype(np.int64)


def primitive_patch(
    kind: str,
    span_u: float,
    span_v: float,
    resolution: int = 200,
    *,
    radius: float = 12.5,
    half_angle: float = np.radians(30.0),
    apex_distance: float = 20.0,
    major_radius: float = 18.0,
    minor_radius: float = 3.0,
) -> Patch:
    """A patch in canonical position (axis = Z, centre = origin).

    For plane, `span_u` and `span_v` are lengths in mm; for the other kinds `span_u`
    is the angle around the axis (radians) and `span_v` the length along the axis
    (cylinder, cone) or the latitude or tube angle (sphere, torus).
    """
    u = np.linspace(-span_u / 2, span_u / 2, resolution)
    v = np.linspace(-span_v / 2, span_v / 2, resolution)
    uu, vv = (grid.ravel() for grid in np.meshgrid(u, v, indexing="ij"))
    faces = _grid_faces(resolution, resolution)
    origin = (0.0, 0.0, 0.0)
    z_axis = (0.0, 0.0, 1.0)
    primitive: Primitive
    if kind == "plane":
        points = np.stack([uu, vv, np.zeros_like(uu)], axis=1)
        normals = np.tile([0.0, 0.0, 1.0], (len(uu), 1))
        primitive = Plane(origin=origin, normal=z_axis)
    elif kind == "cylinder":
        points = np.stack([radius * np.cos(uu), radius * np.sin(uu), vv], axis=1)
        normals = np.stack([np.cos(uu), np.sin(uu), np.zeros_like(uu)], axis=1)
        primitive = Cylinder(origin=origin, axis=z_axis, radius=radius)
    elif kind == "sphere":
        points = radius * np.stack(
            [np.cos(vv) * np.cos(uu), np.cos(vv) * np.sin(uu), np.sin(vv)], 1
        )
        normals = points / radius
        primitive = Sphere(center=origin, radius=radius)
    elif kind == "cone":
        height = vv + apex_distance
        rho = height * np.tan(half_angle)
        points = np.stack([rho * np.cos(uu), rho * np.sin(uu), height], axis=1)
        normals = np.stack(
            [
                np.cos(half_angle) * np.cos(uu),
                np.cos(half_angle) * np.sin(uu),
                -np.sin(half_angle) * np.ones_like(uu),
            ],
            axis=1,
        )
        primitive = Cone(apex=origin, axis=z_axis, half_angle=float(half_angle))
    elif kind == "torus":
        ring = major_radius + minor_radius * np.cos(vv)
        points = np.stack([ring * np.cos(uu), ring * np.sin(uu), minor_radius * np.sin(vv)], axis=1)
        normals = np.stack([np.cos(vv) * np.cos(uu), np.cos(vv) * np.sin(uu), np.sin(vv)], axis=1)
        primitive = Torus(
            center=origin, axis=z_axis, major_radius=major_radius, minor_radius=minor_radius
        )
    else:
        raise ValueError(f"unknown primitive kind {kind!r}")
    return Patch(points, faces, normals, primitive)


def sphere_scan(
    radius: float = 20.0,
    subdivisions: int = 5,
    sigma: float = 0.0,
    seed: int = 1,
) -> tuple[FloatArray, IntArray]:
    """A closed icosphere (20 x 4^subdivisions faces), optionally with scanner noise."""
    import trimesh

    mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    if sigma > 0:
        rng = np.random.default_rng(seed)
        vertices = add_scanner_noise(vertices, vertices / radius, sigma, rng)
    return vertices, np.asarray(mesh.faces, dtype=np.int64)


def box_scan(
    size: tuple[float, float, float] = (100.0, 70.0, 20.0),
    max_edge: float = 2.0,
    sigma: float = 0.0,
    seed: int = 1,
) -> tuple[FloatArray, IntArray]:
    """A closed box with its minimum corner at the origin, subdivided to `max_edge`."""
    import trimesh

    box = trimesh.creation.box(extents=size)
    box.apply_translation(np.asarray(size) / 2)
    vertices, faces = trimesh.remesh.subdivide_to_size(box.vertices, box.faces, max_edge=max_edge)
    mesh = trimesh.Trimesh(vertices, faces, process=True)
    points = np.asarray(mesh.vertices, dtype=np.float64)
    if sigma > 0:
        rng = np.random.default_rng(seed)
        points = add_scanner_noise(points, np.asarray(mesh.vertex_normals), sigma, rng)
    return points, np.asarray(mesh.faces, dtype=np.int64)


def write_binary_stl(path: Path, vertices: FloatArray, faces: IntArray) -> Path:
    """Write a binary STL (triangle soup, as scanners export it)."""
    triangles = vertices[faces].astype(np.float32)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = (normals / np.where(length == 0, 1, length)).astype(np.float32)
    record = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
    data = np.zeros(len(faces), dtype=record)
    data["normal"] = normals
    data["corners"] = triangles
    header = b"Mesh-to-CAD synthetic test mesh".ljust(80, b" ")
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(np.uint32(len(faces)).tobytes())
        handle.write(data.tobytes())
    return path
