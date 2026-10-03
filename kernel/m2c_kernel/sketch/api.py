"""Public API of section sketches.

Pipeline (research: `.work/research/algorithms-cad.md` section 1): a section in an
explicit plane frame; noise from the raw section points and a tolerance of
max(6 sigma, 0.05 mm); a dynamic-programming split into lines and arcs; constraint
inference; a joint least-squares refit; value snapping; exact junctions. The
stored entities are authoritative: `evaluate` builds profile faces from them and
only compares them with the current section.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.sketch import ErrorCode
from m2c_kernel.document.results import Construction, PlaneFrame, SketchResult
from m2c_kernel.fitting.primitives import Axis, Cone, Cylinder, Plane, Torus
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.sketch import autofit, deviation
from m2c_kernel.sketch.convert import InvalidSketchError, to_params, to_work
from m2c_kernel.sketch.model import FloatArray, Point, WorkSketch, entity_polyline
from m2c_kernel.sketch.noise import section_noise as noise_of
from m2c_kernel.sketch.noise import suggested_tolerance
from m2c_kernel.sketch.params import (
    AxisNormalSource,
    FeaturePlaneSource,
    RotationalSection,
    SketchParams,
    SketchSection,
    StandardPlaneSource,
)
from m2c_kernel.sketch.profile import Profile, analyse
from m2c_kernel.sketch.section import (
    STANDARD_FRAMES,
    Section,
    nearest_axis_point,
    planar_section,
    plane_frame,
    rotational_frame,
    rotational_section,
    to_xyz,
    unit3,
)
from m2c_kernel.sketch.to_occ import ProfileError, line_ends, profile_faces
from m2c_kernel.snapping import SnapUnits

__all__ = [
    "EntityFit",
    "FitResult",
    "SectionGeometry",
    "SketchEvaluation",
    "SketchProfiles",
    "auto_fit",
    "cut",
    "deviation_from",
    "evaluate",
    "fit_entity",
    "fit_tolerance",
    "section_geometry",
]

type ConstructionLookup = Callable[[str], Construction]
type IntArray = npt.NDArray[np.int64]

EntityFit = deviation.EntityFit

STANDARD_AXES: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}


@dataclass(frozen=True)
class SketchProfiles(SketchResult):
    """`SketchResult` plus what solid features need to name faces and find axes.

    `edge_names` holds, per profile face, the entity id of each edge in explorer
    order; `lines` the start and end of every sketch line in part coordinates.
    """

    edge_names: tuple[tuple[str, ...], ...] = ()
    lines: Mapping[str, tuple[FloatArray, FloatArray]] = field(default_factory=dict)


@dataclass(frozen=True)
class SectionGeometry:
    """Where a sketch lies and where the scan is cut."""

    frame: PlaneFrame
    cut_offset: float
    """Distance of the cut from the sketch plane along its normal (planar sections)."""
    base_origin: FloatArray
    """Origin of the source plane before the sketch offset (for the offset handle)."""
    offset_direction: FloatArray
    rotational: bool


# --------------------------------------------------------------------------- frames


def _axis(reference: str, construction: ConstructionLookup) -> tuple[FloatArray, FloatArray]:
    """Point and unit direction of a global axis or of a feature that provides one."""
    if reference in STANDARD_AXES:
        return np.zeros(3), np.asarray(STANDARD_AXES[reference], dtype=np.float64)
    item = construction(reference)
    if item.axis is not None:
        return _axis_of(item.axis)
    primitive = item.primitive
    if isinstance(primitive, Cylinder):
        return np.asarray(primitive.origin), unit3(primitive.axis)
    if isinstance(primitive, Cone):
        return np.asarray(primitive.apex), unit3(primitive.axis)
    if isinstance(primitive, Torus):
        return np.asarray(primitive.center), unit3(primitive.axis)
    raise KernelError(ErrorCode.NOT_AN_AXIS, {"feature": reference})


def _axis_of(axis: Axis) -> tuple[FloatArray, FloatArray]:
    return np.asarray(axis.point, dtype=np.float64), unit3(axis.direction)


def section_geometry(section: SketchSection, construction: ConstructionLookup) -> SectionGeometry:
    """Resolve the sketch frame of a planar or rotational section."""
    if isinstance(section, RotationalSection):
        point, direction = _axis(section.axis, construction)
        frame = rotational_frame(point, direction, section.angle_deg)
        return SectionGeometry(frame, 0.0, frame.origin, frame.normal, True)
    source = section.plane
    default_x: Any = None
    if isinstance(source, StandardPlaneSource):
        x, y = (np.asarray(v, dtype=np.float64) for v in STANDARD_FRAMES[source.plane])
        origin, normal, default_x = np.zeros(3), np.cross(x, y), x
    elif isinstance(source, FeaturePlaneSource):
        primitive = construction(source.feature).primitive
        if not isinstance(primitive, Plane):
            raise KernelError(ErrorCode.NOT_A_PLANE, {"feature": source.feature})
        normal = unit3(primitive.normal)
        origin = normal * float(np.asarray(primitive.origin) @ normal)
    else:
        assert isinstance(source, AxisNormalSource)
        point, normal = _axis(source.axis, construction)
        origin = nearest_axis_point(point, normal)
    frame = plane_frame(
        origin, normal, section.offset, section.x_direction, section.flip, default_x
    )
    return SectionGeometry(frame, section.section_offset, origin, normal, False)


def cut(
    vertices: FloatArray,
    faces: IntArray,
    geometry: SectionGeometry,
    normals: FloatArray | None = None,
) -> Section:
    """The section of the scan for a sketch (all arrays in part coordinates).

    Vertex normals let planar sections fit to a band of scan points around the cut.
    """
    if geometry.rotational:
        return rotational_section(vertices, faces, geometry.frame)
    return planar_section(vertices, faces, geometry.frame, geometry.cut_offset, normals)


# --------------------------------------------------------------------------- fitting


@dataclass(frozen=True)
class FitResult:
    """A fitted sketch with the fit quality of each entity and its profile state."""

    params: SketchParams
    fits: list[EntityFit]
    profile: Profile
    noise: float
    tolerance: float


def _working(params: SketchParams) -> tuple[WorkSketch, list[Any]]:
    try:
        return to_work(params)
    except InvalidSketchError as failure:
        raise KernelError(ErrorCode.INVALID_GEOMETRY, details=str(failure)) from failure


def fit_tolerance(params: SketchParams, section: Section) -> tuple[float, float]:
    """(noise, tolerance) of a sketch: the stored noise, or measured on the section."""
    noise = params.noise if params.noise is not None else noise_of(section)
    tolerance = params.tolerance if params.tolerance is not None else suggested_tolerance(noise)
    return noise, tolerance


def auto_fit(params: SketchParams, section: Section, units: SnapUnits, refit: bool) -> FitResult:
    """A new fit of the section, or (`refit`) the edited sketch moved onto the section.

    A new fit replaces entities, constraints, snaps and typed dimensions; rejected
    snaps stay rejected. A refit keeps all of them.
    """
    if section.empty:
        raise KernelError(ErrorCode.EMPTY_SECTION)
    if refit:
        noise, tolerance = fit_tolerance(params, section)
        sketch, constraints = _working(params)
        known = set(sketch.entities)
        snaps = [s for s in params.snaps if s.entity in known]
        dimensions = [d for d in params.dimensions if d.entity in known]
        autofit.refit(sketch, constraints, snaps, dimensions, section, tolerance)
        result = replace(
            to_params(params, sketch, constraints, snaps), dimensions=dimensions, noise=noise
        )
    else:
        outcome = autofit.fit_section(section, params.tolerance, units, params.rejected_snaps)
        sketch, noise, tolerance = outcome.sketch, outcome.noise, outcome.tolerance
        base = replace(params, noise=noise, dimensions=[])
        result = to_params(base, sketch, outcome.constraints, outcome.snaps)
    fits = deviation.entity_fits(sketch, autofit.fit_points(section), tolerance)
    return FitResult(result, fits, analyse(sketch), noise, tolerance)


def fit_entity(
    params: SketchParams,
    section: Section,
    points: FloatArray,
    kind: Literal["auto", "line", "arc"],
) -> tuple[SketchParams, str, float]:
    """Add one line or arc fitted through painted section points; returns its id and deviation."""
    if len(points) < 2 or (kind == "arc" and len(points) < 3):
        raise KernelError(ErrorCode.TOO_FEW_POINTS, {"count": len(points)})
    _, tolerance = fit_tolerance(params, section)
    sketch, constraints = _working(params)
    entity, start, end, max_error = autofit.fit_single(points, kind, tolerance)
    ids = autofit.IdSource([*sketch.points, *sketch.entities])
    start_id, end_id, entity_id = ids.take("p"), ids.take("p"), ids.take("e")
    sketch.points[start_id] = Point(start_id, start)
    sketch.points[end_id] = Point(end_id, end)
    sketch.entities[entity_id] = replace(entity, id=entity_id, start=start_id, end=end_id)
    return to_params(params, sketch, constraints), entity_id, max_error


# --------------------------------------------------------------------------- evaluation


@dataclass(frozen=True)
class SketchEvaluation:
    """What a rebuild derives from the stored entities."""

    profiles: SketchProfiles
    profile: Profile
    segments: FloatArray
    """(s, 2, 3) display segments in part coordinates."""
    segment_entities: npt.NDArray[np.uint32]
    """Entity index (into the stored entity list) per segment."""
    gaps: FloatArray
    """(g, 3) chain ends in part coordinates."""
    invalid_loops: list[str]


def evaluate(params: SketchParams, geometry: SectionGeometry) -> SketchEvaluation:
    """Profile faces and display geometry of the stored entities (no fitting)."""
    sketch, _ = _working(params)
    profile = analyse(sketch)
    frame = geometry.frame
    faces = []
    invalid: list[str] = []
    loops = profile.loops
    while True:
        try:
            faces = profile_faces(sketch, loops, frame)
            break
        except ProfileError as failure:
            invalid.append(failure.loop)
            loops = [loop for loop in loops if loop.id != failure.loop]
    segments: list[FloatArray] = []
    owners: list[int] = []
    for index, entity in enumerate(sketch.entities.values()):
        polyline = to_xyz(frame, entity_polyline(sketch, entity))
        segments.append(np.stack([polyline[:-1], polyline[1:]], axis=1))
        owners += [index] * (len(polyline) - 1)
    profiles = SketchProfiles(
        frame=frame,
        profile_faces=tuple(f.face for f in faces),
        loop_ids=tuple(f.loop_id for f in faces),
        edge_names=tuple(f.edge_names for f in faces),
        lines=line_ends(sketch, frame),
    )
    gaps = to_xyz(frame, np.array(profile.gaps)) if profile.gaps else np.zeros((0, 3))
    return SketchEvaluation(
        profiles,
        profile,
        np.concatenate(segments) if segments else np.zeros((0, 2, 3)),
        np.asarray(owners, dtype=np.uint32),
        gaps,
        invalid,
    )


def deviation_from(params: SketchParams, section: Section) -> float | None:
    """Largest median distance of the fitted entities from the section; None if it is empty."""
    sketch, _ = _working(params)
    if section.empty:
        return None
    return deviation.sketch_deviation(sketch, section)
