"""Scan-like test meshes with known primitives, and documents that hold them."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import numpy.typing as npt

from m2c_kernel.document.model import Document, DocumentSettings, Scan, ScanSource
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.api import Cone, Cylinder, Plane, Primitive, Sphere, Torus
from m2c_kernel.geometry import vec3
from m2c_kernel.session.session import Session
from tests.synthetic import add_scanner_noise, primitive_patch, random_pose

SIGMA = 0.03
SPIKES = 0.01

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class NoisyPatch:
    """A noisy patch in a random pose and the exact primitive it was sampled from."""

    vertices: FloatArray
    faces: IntArray
    truth: Primitive

    def mesh(self, key: str = "mesh:test") -> EvalMesh:
        return EvalMesh(key, self.vertices, self.faces, None)


def posed(primitive: Primitive, rotation: FloatArray, offset: FloatArray) -> Primitive:
    """The primitive after `p -> rotation @ p + offset`."""

    def point(value: tuple[float, float, float]) -> tuple[float, float, float]:
        return vec3(rotation @ np.asarray(value) + offset)

    def direction(value: tuple[float, float, float]) -> tuple[float, float, float]:
        return vec3(rotation @ np.asarray(value))

    match primitive:
        case Plane(origin=o, normal=n):
            return Plane(origin=point(o), normal=direction(n))
        case Cylinder(origin=o, axis=a, radius=r):
            return Cylinder(origin=point(o), axis=direction(a), radius=r)
        case Cone(apex=v, axis=a, half_angle=angle):
            return Cone(apex=point(v), axis=direction(a), half_angle=angle)
        case Sphere(center=c, radius=r):
            return Sphere(center=point(c), radius=r)
        case Torus(center=c, axis=a, major_radius=big, minor_radius=small):
            return Torus(center=point(c), axis=direction(a), major_radius=big, minor_radius=small)


def noisy_patch(
    kind: str,
    span_u: float,
    span_v: float,
    seed: int,
    *,
    resolution: int = 200,
    sigma: float = SIGMA,
    spikes: float = SPIKES,
    pose: bool = True,
    **shape: Any,
) -> NoisyPatch:
    """A 40k-vertex patch with scanner noise (1 % spikes by default) in a random pose."""
    rng = np.random.default_rng(seed)
    patch = primitive_patch(kind, span_u, span_v, resolution, **shape)
    vertices = add_scanner_noise(patch.vertices, patch.normals, sigma, rng, spike_fraction=spikes)
    if not pose:
        return NoisyPatch(vertices, patch.faces, patch.primitive)
    vertices, _, rotation, offset = random_pose(vertices, patch.normals, rng)
    return NoisyPatch(vertices, patch.faces, posed(patch.primitive, rotation, offset))


def angle_deg(a: npt.ArrayLike, b: npt.ArrayLike) -> float:
    """Sign-free angle between two directions."""
    u, v = np.asarray(a, float), np.asarray(b, float)
    cosine = abs(float(u @ v)) / float(np.linalg.norm(u) * np.linalg.norm(v))
    return float(np.degrees(np.arccos(min(cosine, 1.0))))


def line_distance(
    point: npt.ArrayLike, line_point: npt.ArrayLike, direction: npt.ArrayLike
) -> float:
    """Distance of a point from a line."""
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    w = np.asarray(point, float) - np.asarray(line_point, float)
    return float(np.linalg.norm(w - (w @ d) * d))


def combine(*parts: tuple[FloatArray, IntArray]) -> tuple[FloatArray, IntArray]:
    """One mesh from several (vertices, faces) parts."""
    vertices, faces, base = [], [], 0
    for part_vertices, part_faces in parts:
        vertices.append(part_vertices)
        faces.append(part_faces + base)
        base += len(part_vertices)
    return np.concatenate(vertices), np.concatenate(faces)


def scan_document(
    session: Session,
    vertices: FloatArray,
    faces: IntArray,
    *,
    synthetic: npt.NDArray[np.bool_] | None = None,
    settings: DocumentSettings | None = None,
) -> Document:
    """A document whose scan is the given mesh in part coordinates (no alignment)."""
    origin = np.round(vertices.mean(axis=0), 1)
    vertex_ref = session.blobs.put((vertices - origin).astype(np.float32))
    face_ref = session.blobs.put(faces.astype(np.uint32))
    synthetic_ref = None
    if synthetic is not None and synthetic.any():
        synthetic_ref = session.blobs.put(synthetic.astype(np.uint8))
    key = hashlib.sha256(f"{vertex_ref}|{face_ref}|{synthetic_ref}".encode()).hexdigest()[:24]
    scan = Scan(
        key=f"scan:{key}",
        source=ScanSource(file_name="test.stl", sha256="0" * 64, import_unit="mm"),
        vertices=vertex_ref,
        faces=face_ref,
        synthetic=synthetic_ref,
        vertex_count=len(vertices),
        face_count=len(faces),
        origin=vec3(origin),
        noise=SIGMA,
    )
    return replace(Document.empty(), scan=scan, settings=settings or DocumentSettings())
