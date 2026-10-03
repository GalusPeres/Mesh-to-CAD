"""Shape recognition: the base planes of the scan and the features on them.

`recognize.run` reads the aligned scan like a designer (`recognition/api.py`): flat
faces, and on them buttons, bosses, pockets, recesses and holes with fitted outlines
and design intent. Large scans are read from the reduced copy the segmentation also
uses. The result carries the outlines in part coordinates for the viewport (a ring
at the foot and one at the top of every feature) and the numbers for the panel and
for automation clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.codes.regions import ErrorCode
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, U32Array
from m2c_kernel.recognition.api import Recognition, recognize
from m2c_kernel.recognition.outline import ShapeKind
from m2c_kernel.segmentation.lod import LEVELS_OF_DETAIL
from m2c_kernel.session.jobs import JobContext

DEFAULT_NOISE_MM = 0.03


@dataclass(frozen=True, kw_only=True)
class RecognizeParams:
    scan_key: str


@dataclass(frozen=True)
class RecognizedPlane:
    origin: Vec3
    normal: Vec3
    """Unit normal, out of the material."""
    x_axis: Vec3
    area: float
    rms: float


@dataclass(frozen=True)
class RecognizedFeature:
    """A feature on a base plane; lengths in mm, angles in radians, plane frame."""

    plane: int
    kind: Literal["boss", "pocket"]
    shape: ShapeKind
    params: dict[str, float]
    level: float
    """Height of the plane the feature stands on, above its base plane."""
    height: float
    """Height of a boss, depth of a pocket (from its level)."""
    top: Literal["flat", "domed", "through"]
    rms: float
    """RMS distance of the measured contour to the fitted outline."""
    parent: int | None
    """The pocket the feature stands in."""
    group: int
    """Features of the same shape and size share a group number."""
    label: Vec3
    """Where to put the feature's label (top centre, part coordinates)."""


@dataclass(frozen=True)
class RecognizeResult:
    planes: list[RecognizedPlane]
    features: list[RecognizedFeature]
    outlines: F32Array
    """(k, 3) outline points; feature i has the rings 2i (foot) and 2i + 1 (top)."""
    outline_offsets: U32Array
    """(2 x features + 1,) start of every ring in `outlines`."""


@command("recognize.run", lane=True, exclusive=True)
def recognize_run(ctx: JobContext, params: RecognizeParams) -> RecognizeResult:
    """Recognise the base planes and features of the current, aligned scan."""
    session = ctx.session
    scan = session.document.scan
    if scan is None:
        raise KernelError(ErrorCode.NO_SCAN)
    if params.scan_key != scan.key:
        raise KernelError(ErrorCode.STALE_SCAN, {"scanKey": params.scan_key})
    built = session.built(ctx).result
    mesh = built.mesh
    if mesh is None:
        raise KernelError(ErrorCode.NO_SCAN)
    working = LEVELS_OF_DETAIL.get(mesh, scan.key, built.matrix, ctx)
    # Filled holes are not part of the scanned surface.
    faces = working.faces[~working.synthetic]
    noise = scan.noise if scan.noise else DEFAULT_NOISE_MM
    recognition = recognize(working.vertices, faces, float(noise), ctx.check_cancelled)
    return _result(recognition)


def _vec3(values: np.ndarray) -> Vec3:
    return float(values[0]), float(values[1]), float(values[2])


def _result(recognition: Recognition) -> RecognizeResult:
    groups: dict[tuple[object, ...], int] = {}
    features: list[RecognizedFeature] = []
    rings: list[np.ndarray] = []
    for feature in recognition.features:
        relief = feature.relief
        outline = feature.outline
        values = outline.named()
        size = tuple(
            round(value, 3)
            for name, value in values.items()
            if name not in ("cx", "cy", "angle", "start")
        )
        key = (feature.plane, relief.kind, outline.kind, size, round(relief.height, 3))
        group = groups.setdefault(key, len(groups))
        sign = 1.0 if relief.kind == "boss" else -1.0
        top = relief.level + sign * relief.height
        foot = recognition.outline_3d(feature, relief.level)
        head = recognition.outline_3d(feature, top)
        rings.extend([foot, head])
        features.append(
            RecognizedFeature(
                plane=feature.plane,
                kind=relief.kind,
                shape=outline.kind,
                params={name: float(value) for name, value in values.items()},
                level=float(relief.level),
                height=float(relief.height),
                top=relief.top,
                rms=float(outline.rms),
                parent=relief.parent,
                group=group,
                label=_vec3(head.mean(axis=0)),
            )
        )
    sizes = [len(ring) for ring in rings]
    offsets = np.concatenate([[0], np.cumsum(sizes)]).astype(np.uint32)
    points = np.concatenate(rings) if rings else np.zeros((0, 3))
    return RecognizeResult(
        planes=[
            RecognizedPlane(
                origin=_vec3(plane.origin),
                normal=_vec3(plane.normal),
                x_axis=_vec3(plane.x_axis),
                area=float(plane.area),
                rms=float(plane.rms),
            )
            for plane in recognition.planes
        ],
        features=features,
        outlines=points.astype(np.float32),
        outline_offsets=offsets,
    )
