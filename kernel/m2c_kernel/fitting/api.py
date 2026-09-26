"""Public API of primitive fitting, used by features, commands, segmentation and alignment.

Conventions: part coordinates in millimetres, angles in radians, primitive
parameters and signed distances as in `m2c_kernel.fitting.primitives`. Pass jet
normals (`EvalMesh.jet.normals`), not raw vertex normals, and a random generator
seeded from the request or result key so results are reproducible.
"""

from __future__ import annotations

import numpy as np

from m2c_kernel.fitting.constrained import (
    ConstrainedFit,
    Constraints,
    direction_of,
    refine_constrained,
)
from m2c_kernel.fitting.display import PatchGeometry, axis_segment, plane_patch, primitive_patch
from m2c_kernel.fitting.fit import (
    FitError,
    FitResult,
    fit_best,
    fit_primitive,
    robust_sigma,
    statistics,
    trial_fits,
)
from m2c_kernel.fitting.intent import (
    GLOBAL_AXES,
    AppliedSnap,
    AxisName,
    SnapId,
    angle_to_axis_deg,
    cluster_directions,
    parallel_global_axis,
    snap_fit,
)
from m2c_kernel.fitting.pipeline import (
    FaceState,
    FitAlternative,
    FitOutcome,
    FitRequest,
    FitStats,
    applicable_kinds,
    run_fit,
)
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
from m2c_kernel.fitting.ransac import RansacResult, ransac
from m2c_kernel.geometry import FloatArray

__all__ = [
    "GLOBAL_AXES",
    "PRIMITIVE_KINDS",
    "AppliedSnap",
    "Axis",
    "AxisName",
    "Cone",
    "ConstrainedFit",
    "Constraints",
    "Cylinder",
    "FaceState",
    "FitAlternative",
    "FitError",
    "FitOutcome",
    "FitRequest",
    "FitResult",
    "FitStats",
    "PatchGeometry",
    "Plane",
    "Primitive",
    "PrimitiveKind",
    "RansacResult",
    "SnapId",
    "Sphere",
    "Torus",
    "angle_to_axis_deg",
    "applicable_kinds",
    "axis_segment",
    "cluster_directions",
    "direction_of",
    "fit_best",
    "fit_primitive",
    "fit_robust",
    "parallel_global_axis",
    "plane_patch",
    "primitive_patch",
    "ransac",
    "refine_constrained",
    "robust_sigma",
    "run_fit",
    "signed_distance",
    "snap_fit",
    "surface_normals",
    "trial_fits",
]


def fit_robust(
    kind: PrimitiveKind,
    points: FloatArray,
    normals: FloatArray,
    threshold: float,
    rng: np.random.Generator,
) -> FitResult:
    """Fit with outlier rejection (LO-RANSAC), for selections that include other surfaces.

    `threshold` is the inlier distance in mm (about three times the scan noise).
    The statistics are those of the consensus set.
    """
    result = ransac(kind, points, normals, threshold, rng)
    return statistics(result.fit.primitive, points[result.inliers])
