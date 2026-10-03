"""Public API of automatic freeform surfacing.

`auto_surface` turns a scan (or a connected part of it) into a network of bicubic
B-spline patches, sewn by construction into a closed solid, or an open shell when the
scan is open. Stages and the measurements behind the constants:

1. Cage: quadric decimation to an intermediate size, then a manifold-preserving edge
   collapse to `SurfacingOptions.cage_triangles` triangles (`cage.py`, `collapse.py`).
2. One Catmull-Clark step makes the cage all-quad (three quads per triangle).
3. Fit: `FIT_ITERATIONS` rounds of sparse least squares on the limit surface sampled on
   a 5 x 5 grid per quad (`fitting.py`). On the Armadillo (346 k triangles) the RMS
   distance of the scan to the surface falls from 1.9 mm (unfitted cage) to 0.30 mm at
   1000 cage triangles; more rounds gain less than 3 %.
4. Patches: every cage quad becomes a bicubic patch through a 9 x 9 grid of exact limit
   points (`patches.py`). Measured on the Armadillo, the patches stay within 0.04 mm of
   the limit surface (99 % within 0.0011 mm), and neighbouring patches meet with a
   normal difference below 0.33 degrees for 99 % of the edge points away from the
   corners. At extraordinary cage vertices (valence 6 and more) bicubic patches cannot
   follow the curvature spike of the limit surface, so the normals of the patches around
   such a vertex differ in a small corner zone: 90 % of the corner points below 3.1
   degrees, the worst 62 degrees at a valence-12 vertex, and below 1 degree within 15 %
   of a patch side from the corner.
5. Shape: faces, edges and vertices built directly from the quad topology (`brep.py`).
6. Deviation: distances of the scan vertices to the final patches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from m2c_kernel.cad.occ_compat import BRepCheck_Analyzer
from m2c_kernel.codes.surfacing import ErrorCode, ProgressStage
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.mesh.normals import vertex_normals
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.surfacing.brep import build_shape
from m2c_kernel.surfacing.cage import (
    CageError,
    Decimator,
    compact,
    decimated_cage,
    face_components,
)
from m2c_kernel.surfacing.fitting import FitProgress, fit_cage, scan_samples
from m2c_kernel.surfacing.patches import PatchNetwork, interpolate_patches
from m2c_kernel.surfacing.subdivision import (
    catmull_clark,
    edge_topology,
    patch_hierarchy,
)

if TYPE_CHECKING:
    from m2c_kernel.session.jobs import JobContext

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]
type Detail = Literal["coarse", "medium", "fine"]
type Smoothing = Literal["low", "medium", "high"]

CAGE_TRIANGLES: dict[str, int] = {"coarse": 400, "medium": 1000, "fine": 2500}
"""Cage triangles per detail level; the surface gets three patches per triangle."""
SMOOTHING_WEIGHT: dict[str, float] = {"low": 0.002, "medium": 0.01, "high": 0.05}
"""Fairness weight per smoothing level (see `fitting.fit_cage`)."""

MIN_FACES = MIN_FIT_FACES
"""Smallest scan part or selection (the same limit as for shape fitting)."""
FIT_LEVEL = 2
PATCH_LEVEL = 3
FIT_ITERATIONS = 6
MAX_FIT_POINTS = 400_000
DEVIATION_SAMPLES = 17
"""Samples per patch side for the deviation statistics."""
MIN_PART_SHARE = 0.01
"""Other parts count as ignored (issue) when they have at least this share of the faces."""
SHAPE_TOLERANCE = 1e-6
"""Tolerance of the new B-Rep vertices, edges and faces (mm)."""


@dataclass(frozen=True)
class SurfacingOptions:
    """Size of the triangle cage, fairness weight and number of fit rounds."""

    cage_triangles: int
    smoothing: float
    iterations: int = FIT_ITERATIONS

    @classmethod
    def from_levels(cls, detail: Detail, smoothing: Smoothing) -> SurfacingOptions:
        """Options for the detail and smoothing levels offered in the application."""
        return cls(cage_triangles=CAGE_TRIANGLES[detail], smoothing=SMOOTHING_WEIGHT[smoothing])


@dataclass(frozen=True)
class DeviationStats:
    """Unsigned distances of scan vertices to the surface (mm)."""

    rms: float
    mean: float
    p95: float
    max: float
    count: int


@dataclass(frozen=True)
class SurfaceModel:
    """Result of `auto_surface`.

    Attributes:
        shape: A `TopoDS_Solid` when `closed`, otherwise a `TopoDS_Shell`.
        closed: Whether the patches enclose a volume.
        faces: The B-Rep face of every patch, in patch order.
        network: Poles of every patch.
        cage_vertices: Fitted control cage (quad mesh), for display.
        cage_quads: Its quads; patch i belongs to quad i.
        deviation: Scan-to-surface distances of the surfaced part.
        ignored_parts: Other connected parts of the input (with at least 1 % of its faces).
    """

    shape: Any
    closed: bool
    faces: tuple[Any, ...]
    network: PatchNetwork
    cage_vertices: FloatArray
    cage_quads: IntArray
    deviation: DeviationStats
    ignored_parts: int

    @property
    def patch_count(self) -> int:
        """Number of B-spline faces."""
        return len(self.faces)


def auto_surface(
    vertices: FloatArray,
    faces: IntArray,
    options: SurfacingOptions,
    job: JobContext,
    synthetic: BoolArray | None = None,
    decimate: Decimator | None = None,
) -> SurfaceModel:
    """Fit a B-spline patch network to the largest connected part of a triangle mesh.

    Args:
        vertices: (n, 3) scan vertices in part coordinates.
        faces: (m, 3) triangles, counter-clockwise seen from outside.
        options: Cage size, smoothing and iteration count.
        job: Progress and cancellation.
        synthetic: Per face, True for triangles made by hole filling. They are surfaced
            (they close the part) but their vertices do not count in the deviation.
        decimate: Replaces the decimation in a child process (tests).

    Raises:
        KernelError: `surfacing.tooFewFaces`, `surfacing.cageFailed` or
            `surfacing.shapeInvalid`.
    """
    if len(faces) < MIN_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(faces), "min": MIN_FACES})
    part, ignored = _largest_part(faces, len(vertices))
    part_vertices, part_faces = compact(vertices, faces[part])
    measured = np.ones(len(part_vertices), dtype=bool)
    if synthetic is not None and np.any(synthetic[part]):
        measured[:] = False
        measured[part_faces[~synthetic[part]].ravel()] = True
    if len(part_faces) < MIN_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(part_faces), "min": MIN_FACES})

    job.progress(0.0, ProgressStage.CAGE)
    normals = vertex_normals(part_vertices, part_faces)
    stride = max(1, -(-len(part_vertices) // MAX_FIT_POINTS))
    scan = scan_samples(part_vertices[::stride], normals[::stride])
    try:
        cage = decimated_cage(
            part_vertices,
            part_faces,
            options.cage_triangles,
            decimate or _child_process_decimator(job),
            job.check_cancelled,
        )
    except CageError as error:
        raise KernelError(ErrorCode.CAGE_FAILED, details=str(error)) from error

    job.progress(0.1, ProgressStage.FITTING)
    step = catmull_clark(cage.faces, len(cage.vertices))
    quads = step.quads
    cage_vertices = step.matrix @ cage.vertices

    def fit_progress(state: FitProgress) -> None:
        job.progress(0.1 + 0.4 * state.iteration / state.iterations, ProgressStage.FITTING)

    fitted = fit_cage(
        cage_vertices,
        quads,
        patch_hierarchy(quads, len(cage_vertices), FIT_LEVEL),
        scan,
        smoothing=options.smoothing,
        iterations=options.iterations,
        check_cancelled=job.check_cancelled,
        progress=fit_progress,
    )

    job.progress(0.5, ProgressStage.PATCHES)
    hierarchy = patch_hierarchy(quads, len(fitted), PATCH_LEVEL)
    network = interpolate_patches(hierarchy.limit_points(fitted)[hierarchy.grids])

    job.progress(0.55, ProgressStage.SHAPE)
    patch_shape = build_shape(
        network,
        quads,
        edge_topology(quads, len(fitted)),
        SHAPE_TOLERANCE,
        job.check_cancelled,
    )
    if not BRepCheck_Analyzer(patch_shape.shape).IsValid():
        raise KernelError(ErrorCode.SHAPE_INVALID)

    job.progress(0.85, ProgressStage.DEVIATION)
    deviation = surface_deviation(network, part_vertices[measured])
    job.progress(1.0, ProgressStage.DEVIATION)
    return SurfaceModel(
        shape=patch_shape.shape,
        closed=patch_shape.closed,
        faces=patch_shape.faces,
        network=network,
        cage_vertices=fitted,
        cage_quads=quads,
        deviation=deviation,
        ignored_parts=ignored,
    )


def surface_deviation(network: PatchNetwork, points: FloatArray) -> DeviationStats:
    """Distances of `points` to the patches: nearest dense surface sample, then its plane.

    The samples lie 1/16 of a patch side apart; the plane through the nearest one
    differs from the true foot point by far less than the scan noise.
    """
    parameters = np.linspace(0.0, 1.0, DEVIATION_SAMPLES)
    samples, normals = network.evaluate(parameters)
    samples, normals = samples.reshape(-1, 3), normals.reshape(-1, 3)
    _, index = cKDTree(samples).query(points, workers=-1)
    distance = np.abs(np.einsum("ij,ij->i", points - samples[index], normals[index]))
    return DeviationStats(
        rms=float(np.sqrt(np.mean(distance**2))),
        mean=float(np.mean(distance)),
        p95=float(np.percentile(distance, 95)),
        max=float(np.max(distance)),
        count=len(distance),
    )


def _largest_part(faces: IntArray, n_vertices: int) -> tuple[BoolArray, int]:
    """Faces of the largest connected part, and how many other parts are not negligible."""
    labels = face_components(faces, n_vertices)
    counts = np.bincount(labels)
    largest = int(np.argmax(counts))
    others = np.delete(counts, largest)
    ignored = int(np.count_nonzero(others >= MIN_PART_SHARE * len(faces)))
    return labels == largest, ignored


def _child_process_decimator(job: JobContext) -> Decimator:
    """Decimation in a killable child process (`mesh/decimate.py`)."""
    from m2c_kernel.mesh.decimate import decimate
    from m2c_kernel.mesh.load import RawMesh

    def run(vertices: FloatArray, faces: IntArray, target: int) -> tuple[FloatArray, IntArray]:
        change = decimate(RawMesh(vertices, faces), target, job.check_cancelled)
        return change.mesh.vertices, change.mesh.faces

    return run
