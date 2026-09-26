"""Public API of primitive fitting, used by segmentation, alignment and features.

Conventions: part coordinates in millimetres, angles in radians, primitive
parameters and signed distances as in `m2c_kernel.fitting.primitives`. Pass jet
normals (`EvalMesh.jet.normals`), not raw vertex normals, and a random generator
from `EvalContext.rng` so results are reproducible.
"""

from __future__ import annotations

import numpy as np

from m2c_kernel.fitting.fit import FitError, FitResult, fit_best, fit_primitive, robust_sigma
from m2c_kernel.fitting.primitives import (
    PRIMITIVE_KINDS,
    Axis,
    Cone,
    Cylinder,
    Plane,
    Primitive,
    PrimitiveKind,
    Sphere,
    Torus,
    signed_distance,
    surface_normals,
)
from m2c_kernel.geometry import FloatArray

__all__ = [
    "PRIMITIVE_KINDS",
    "Axis",
    "Cone",
    "Cylinder",
    "FitError",
    "FitResult",
    "Plane",
    "Primitive",
    "PrimitiveKind",
    "Sphere",
    "Torus",
    "fit_best",
    "fit_primitive",
    "fit_robust",
    "robust_sigma",
    "signed_distance",
    "surface_normals",
]


def fit_robust(
    kind: PrimitiveKind,
    points: FloatArray,
    normals: FloatArray,
    threshold: float,
    rng: np.random.Generator,
) -> FitResult:
    """Fit with outlier rejection (LO-RANSAC), for selections that include other surfaces.

    Not implemented yet; see `.work/research/algorithms-mesh.md` 3.4.
    """
    raise NotImplementedError("robust fitting")
