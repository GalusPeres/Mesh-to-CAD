"""Public API of freeform patches and lofts.

- Patches: `fit_scan_patch` fits a P-spline height field to scan triangles and
  converts it exactly to an Open CASCADE B-spline face (`heightfield.py`, `occ.py`).
- Lofts: `loft_scan` sections the scan along an axis and lofts a solid through the
  normalised sections (`sections.py`, `loft.py`).

Measurements behind the defaults: `.work/research/algorithms-cad.md` section 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.freeform import ErrorCode
from m2c_kernel.freeform.heightfield import (
    MAX_NORMAL_SPREAD_DEG,
    MAX_SPANS,
    MIN_SPANS,
    PatchFit,
    fit_patch,
    patch_grid,
)
from m2c_kernel.freeform.loft import LoftAxis, ScanLoft, body_range, loft_scan, scan_extent
from m2c_kernel.freeform.occ import patch_face
from m2c_kernel.geometry import FloatArray
from m2c_kernel.limits import MIN_FIT_FACES
from m2c_kernel.protocol.errors import KernelError

__all__ = [
    "MAX_NORMAL_SPREAD_DEG",
    "MAX_SPANS",
    "MIN_SPANS",
    "PASS_SHARE",
    "LoftAxis",
    "PatchResult",
    "ScanLoft",
    "ScanMesh",
    "body_range",
    "fit_scan_patch",
    "loft_scan",
    "scan_extent",
]

PASS_SHARE = 0.95
"""A result passes when this share of the used triangles lies within the tolerance."""
FAR_FACTOR = 3.0

type IntArray = npt.NDArray[np.int64]


class FaceState:
    """Per-triangle pass/fail state (renderer `FACE_STATE`)."""

    PASS = 1
    FAIL = 2
    FAIL_FAR = 3


class ScanMesh(Protocol):
    """What the freeform functions read from the aligned scan (`EvalMesh`)."""

    vertices: FloatArray
    faces: IntArray
    synthetic: npt.NDArray[np.bool_]

    @property
    def face_centroids(self) -> FloatArray:
        """(m, 3) face centroids."""
        ...

    @property
    def jet(self) -> Any:
        """Jet fit of the scan (`mesh.normals.JetFit`): smoothed normals and the noise."""
        ...


@dataclass(frozen=True)
class PatchResult:
    """A fitted patch with its face, its verdict against the tolerance and its display."""

    fit: PatchFit
    face: Any
    """The patch as a `TopoDS_Face` over its full parameter rectangle."""
    noise: float
    within_tolerance: float
    face_count: int
    used_faces: IntArray
    face_states: npt.NDArray[np.uint8]
    """One `FaceState` per used face."""
    mesh_vertices: FloatArray
    mesh_faces: IntArray
    iso_lines: FloatArray


def fit_scan_patch(
    mesh: ScanMesh,
    faces: IntArray,
    *,
    spans: tuple[int, int] | None,
    smoothing: float,
    margin: float,
    tolerance: float,
    noise: float | None,
) -> PatchResult:
    """Fit a patch to scan triangles (part coordinates) and build its face and display."""
    faces = np.unique(faces[(faces >= 0) & (faces < len(mesh.faces))])
    faces = faces[~mesh.synthetic[faces]]
    if len(faces) < MIN_FIT_FACES:
        raise KernelError(ErrorCode.TOO_FEW_FACES, {"count": len(faces), "min": MIN_FIT_FACES})
    vertex_ids = np.unique(mesh.faces[faces])
    jet = mesh.jet
    fit = fit_patch(mesh.vertices[vertex_ids], jet.normals[vertex_ids], spans, smoothing, margin)
    distance = np.abs(fit.surface.normal_distance(mesh.face_centroids[faces]))
    states = np.full(len(faces), FaceState.FAIL_FAR, dtype=np.uint8)
    states[distance <= FAR_FACTOR * tolerance] = FaceState.FAIL
    states[distance <= tolerance] = FaceState.PASS
    vertices, triangles, lines = patch_grid(fit.surface)
    return PatchResult(
        fit=fit,
        face=patch_face(fit.surface),
        noise=float(noise if noise is not None else jet.noise),
        within_tolerance=float(np.mean(distance <= tolerance)),
        face_count=len(faces),
        used_faces=faces,
        face_states=states,
        mesh_vertices=vertices,
        mesh_faces=triangles,
        iso_lines=lines,
    )
