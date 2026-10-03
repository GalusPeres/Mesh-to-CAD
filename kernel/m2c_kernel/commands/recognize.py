"""Shape recognition: the base planes of the scan and the features on them.

`recognize.run` reads the aligned scan like a designer (`recognition/api.py`): flat
faces, and on them buttons, bosses, pockets, recesses and holes with fitted outlines
and design intent. Scans up to `FULL_DETAIL_FACES` are read as they are (a reduced
copy loses small buttons and makes flat tops look domed); larger ones from the
reduced copy the segmentation also uses. The result carries the outlines in part
coordinates for the viewport (a ring at the foot and one at the top of every
feature) and the numbers for the panel and for automation clients.

`recognize.build` turns chosen features of the last recognition into editable
features (`recognition/build.py`): a plane, sketches and extrusions, added to a body
or as new bodies, in one undoable step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.codes.regions import ErrorCode
from m2c_kernel.document.ops import AddFeature, NewFeature, apply_ops
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, RawObject, U32Array
from m2c_kernel.recognition.api import Recognition, recognize
from m2c_kernel.recognition.build import plan_features, plane_faces
from m2c_kernel.recognition.outline import ShapeKind
from m2c_kernel.segmentation.lod import LEVELS_OF_DETAIL
from m2c_kernel.session.jobs import JobContext

DEFAULT_NOISE_MM = 0.03
FULL_DETAIL_FACES = 1_000_000


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
    """Features of the same shape, size, height and top share a group number (0, 1, ...)."""
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
    real = int((~mesh.synthetic).sum())
    working = (
        mesh
        if real <= FULL_DETAIL_FACES
        else LEVELS_OF_DETAIL.get(mesh, scan.key, built.matrix, ctx)
    )
    # Filled holes are not part of the scanned surface.
    faces = working.faces[~working.synthetic]
    recognition = recognize(working.vertices, faces, _noise(scan.noise), ctx.check_cancelled)
    _LAST.clear()
    _LAST[mesh.key] = recognition
    return _result(recognition)


_LAST: dict[str, Recognition] = {}
"""The last recognition, by the key of the aligned mesh it was made on."""


def _noise(noise: float | None) -> float:
    return float(noise) if noise else DEFAULT_NOISE_MM


@dataclass(frozen=True, kw_only=True)
class BuildParams:
    scan_key: str
    base_revision: int
    features: list[int]
    """Indices into the features of the last `recognize.run`."""
    target_body: str | None = None
    """Body the bosses join and the pockets cut; None adds bosses as new bodies."""
    names: list[str] | None = None
    """Display names of the chosen features (in the order of `features`) for their
    extrusions, in the user's language."""


@dataclass(frozen=True)
class BuildResult:
    revision: int
    added: list[str]
    """Ids of the added features."""
    skipped: list[int]
    """Chosen features that were not built (free profiles; pockets without a body)."""


@command("recognize.build", lane=True, exclusive=True)
def recognize_build(ctx: JobContext, params: BuildParams) -> BuildResult:
    """Build chosen features of the last recognition as plane, sketches and extrusions."""
    session = ctx.session
    document = session.document
    if document.revision != params.base_revision:
        raise KernelError(
            DocumentError.STALE_REVISION,
            {"head": document.revision, "base": params.base_revision},
        )
    scan = document.scan
    if scan is None or params.scan_key != scan.key:
        raise KernelError(ErrorCode.STALE_SCAN, {"scanKey": params.scan_key})
    built = session.built(ctx).result
    mesh = built.mesh
    recognition = _LAST.get(mesh.key) if mesh is not None else None
    if mesh is None or recognition is None:
        raise KernelError(ErrorCode.STALE_SCAN, {"scanKey": params.scan_key})
    count = len(recognition.features)
    if not params.features or any(not 0 <= index < count for index in params.features):
        raise KernelError(ErrorCode.EMPTY_SELECTION)
    if params.target_body is not None and params.target_body not in built.bodies:
        raise KernelError(DocumentError.UNKNOWN_FEATURE, {"feature": params.target_body})

    real = ~mesh.synthetic
    centroids = np.where(real[:, None], mesh.face_centroids, np.inf)
    faces = [
        plane_faces(plane, centroids, mesh.face_normals, _noise(scan.noise))
        for plane in recognition.planes
    ]
    names = dict(zip(params.features, params.names, strict=False)) if params.names else None
    plan = plan_features(
        recognition, params.features, faces, document.next_id, params.target_body, names
    )
    ops = [
        AddFeature(
            feature=NewFeature(
                type=item.type,
                name=item.name,
                params=RawObject(item.params, tuple(memoryview(b) for b in item.buffers)),
            )
        )
        for item in plan.features
    ]
    applied = apply_ops(document, ops, session.feature_types, session.blobs)
    snapshot = session.commit(applied.document, "recognize", ctx)
    added = [feature.id for feature in applied.document.features[len(document.features) :]]
    return BuildResult(revision=snapshot.revision, added=added, skipped=plan.skipped)


def _vec3(values: np.ndarray) -> Vec3:
    return float(values[0]), float(values[1]), float(values[2])


def _result(recognition: Recognition) -> RecognizeResult:
    groups: dict[tuple[object, ...], int] = {}
    features: list[RecognizedFeature] = []
    rings: list[np.ndarray] = []
    for index, feature in enumerate(recognition.features):
        relief = feature.relief
        outline = feature.outline
        values = outline.named()
        size = tuple(
            round(value, 3)
            for name, value in values.items()
            if name not in ("cx", "cy", "angle", "start")
        )
        # Free profiles differ from each other: each is its own group.
        shape = (outline.kind, size) if outline.kind != "profile" else ("profile", index)
        key = (feature.plane, relief.kind, relief.top, shape, round(relief.height, 3))
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
