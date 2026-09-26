"""Noisy synthetic sections and 2D outlines with exact ground truth."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import numpy as np
import numpy.typing as npt

from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.sketch.api import SectionGeometry, cut, section_geometry
from m2c_kernel.sketch.params import PlanarSection, StandardPlaneSource
from m2c_kernel.sketch.section import Section
from tests.synthetic import add_scanner_noise
from tests.synthetic.parts import plate_part

type FloatArray = npt.NDArray[np.float64]

PLATE_SPEC = PlanarSection(plane=StandardPlaneSource(plane="XY"), section_offset=5.0)
"""Sketch on XY, cut through the middle of the 10 mm plate."""

PLATE_CORNERS = np.array(
    [
        (10, 30),
        (-10, 30),
        (-42, 30),
        (-50, 22),
        (-50, -22),
        (-42, -30),
        (42, -30),
        (50, -22),
        (50, 22),
        (42, 30),
    ],
    dtype=np.float64,
)
"""Junctions of the true plate outline: fillet ends, chamfer ends, notch ends."""


def no_constructions(feature_id: str) -> None:
    raise AssertionError(f"unexpected reference {feature_id}")


@dataclass(frozen=True)
class NoisyScan:
    vertices: FloatArray
    faces: npt.NDArray[np.int64]
    normals: FloatArray

    def section(self, geometry: SectionGeometry) -> Section:
        return cut(self.vertices, self.faces, geometry, self.normals)


@cache
def noisy_plate(sigma: float, seed: int = 1) -> NoisyScan:
    part = plate_part()
    rng = np.random.default_rng(seed)
    clean_normals = vertex_normals(part.vertices, part.faces)
    vertices = add_scanner_noise(part.vertices, clean_normals, sigma, rng)
    return NoisyScan(vertices, part.faces, vertex_normals(vertices, part.faces))


def plate_section(sigma: float, seed: int = 1) -> tuple[SectionGeometry, Section]:
    geometry = section_geometry(PLATE_SPEC, no_constructions)  # type: ignore[arg-type]
    return geometry, noisy_plate(sigma, seed).section(geometry)


class Outline:
    """A closed 2D outline built from lines and arcs, sampled densely with normals."""

    def __init__(self, step: float = 0.1) -> None:
        self.step = step
        self.points: list[FloatArray] = []
        self.normals: list[FloatArray] = []

    def line(self, a: tuple[float, float], b: tuple[float, float]) -> Outline:
        start, end = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
        count = max(2, int(np.linalg.norm(end - start) / self.step))
        t = np.linspace(0.0, 1.0, count, endpoint=False)[:, None]
        direction = (end - start) / np.linalg.norm(end - start)
        self.points.append(start + t * (end - start))
        self.normals.append(np.tile([direction[1], -direction[0]], (count, 1)))
        return self

    def arc(
        self, center: tuple[float, float], radius: float, a0_deg: float, a1_deg: float
    ) -> Outline:
        a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
        count = max(3, int(abs(a1 - a0) * radius / self.step))
        t = np.linspace(a0, a1, count, endpoint=False)
        radial = np.column_stack([np.cos(t), np.sin(t)])
        self.points.append(np.asarray(center) + radius * radial)
        # Counter-clockwise outlines: the outward normal is radial on left turns.
        self.normals.append(radial if a1 > a0 else -radial)
        return self

    def noisy(self, sigma: float, seed: int) -> FloatArray:
        rng = np.random.default_rng(seed)
        points, normals = np.vstack(self.points), np.vstack(self.normals)
        return points + normals * rng.normal(0.0, sigma, (len(points), 1))


def circle_points(
    center: tuple[float, float], radius: float, sigma: float, seed: int
) -> FloatArray:
    rng = np.random.default_rng(seed)
    count = max(24, int(2 * math.pi * radius / 0.1))
    t = np.linspace(0.0, 2 * math.pi, count, endpoint=False)
    r = radius + rng.normal(0.0, sigma, count)
    return np.column_stack([center[0] + r * np.cos(t), center[1] + r * np.sin(t)])


def section_of(loops: list[FloatArray], stride: int = 5) -> Section:
    """A section whose cut is every `stride`-th outline point; all points support the fit."""
    return Section([loop[::stride] for loop in loops], [], np.vstack(loops))


type Lookup = Callable[[str], object]
