"""Loft: a solid through sections of the scan along an axis.

Face tags: the lateral faces are `<id>:loft:<n>` (one per edge of the section wires,
normally a single face) and the caps `<id>:cap:start` and `<id>:cap:end`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Annotated

import numpy as np

from m2c_kernel.cad.operations import solid_output
from m2c_kernel.cad.tags import TagCollector
from m2c_kernel.codes.freeform import ErrorCode, ProgressStage
from m2c_kernel.document.results import Body, Construction, DisplaySource, FeatureOutput
from m2c_kernel.features.common import BodyOperation, StandardAxis, feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.fitting.primitives import Cone, Cylinder, Plane, Torus
from m2c_kernel.freeform.api import LoftAxis, ScanLoft, loft_scan
from m2c_kernel.geometry import unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, Range, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore

type SectionCount = Annotated[int, Range(3, 64)]

GLOBAL_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


@dataclass(frozen=True, kw_only=True)
class LoftParams:
    path: StandardAxis | str
    """A global axis or the id of a feature with an axis (a cylinder, cone, torus or axis)."""
    start: float
    end: float
    """Section range along the axis, in mm from the axis point (the origin for X, Y, Z)."""
    section_count: SectionCount = 12
    faces: BlobRef | None = None
    """Only these scan triangles are sectioned (a region); None sections the whole scan."""
    operation: BodyOperation = "newBody"
    target_body: str | None = None


@dataclass(frozen=True, kw_only=True)
class LoftInput:
    path: StandardAxis | str
    start: float
    end: float
    section_count: SectionCount = 12
    faces: U32Array | None = None
    operation: BodyOperation = "newBody"
    target_body: str | None = None


def _store(value: LoftInput, blobs: BlobStore) -> LoftParams:
    faces = None if value.faces is None else blobs.put(np.unique(value.faces).astype(np.uint32))
    return LoftParams(
        path=value.path,
        start=value.start,
        end=value.end,
        section_count=value.section_count,
        faces=faces,
        operation=value.operation,
        target_body=value.target_body,
    )


def loft_axis(path: str, construction_of: Callable[[str], Construction]) -> LoftAxis:
    """The loft axis: a global axis, a fitted axis, a reference axis or a plane normal."""
    if path in GLOBAL_AXES:
        return LoftAxis(np.zeros(3), np.asarray(GLOBAL_AXES[path]))
    construction = construction_of(path)
    match construction.primitive:
        case Cylinder(origin=point, axis=direction) | Torus(center=point, axis=direction):
            return LoftAxis(np.asarray(point), unit(direction))
        case Cone(apex=point, axis=direction):
            return LoftAxis(np.asarray(point), unit(direction))
        case Plane(origin=point, normal=direction):
            return LoftAxis(np.asarray(point), unit(direction))
    if construction.axis is not None:
        axis = construction.axis
        return LoftAxis(np.asarray(axis.point), unit(axis.direction))
    raise KernelError(ErrorCode.NOT_AN_AXIS, {"feature": path})


def tagged_body(loft: ScanLoft, feature_id: str) -> Body:
    collector = TagCollector(loft.solid.shape)
    collector.set(loft.solid.start_cap, f"{feature_id}:cap:start")
    collector.set(loft.solid.end_cap, f"{feature_id}:cap:end")
    for index, face in enumerate(loft.solid.lateral):
        collector.set(face, f"{feature_id}:loft:{index}")
    for index in collector.missing():
        collector.set(collector.face(index), f"{feature_id}:loft:{index}")
    return collector.body()


def section_display(loft: ScanLoft) -> DisplaySource:
    segments = np.concatenate(
        [np.stack([points, np.roll(points, -1, axis=0)], axis=1) for points in loft.sections]
    )
    return DisplaySource(kind="lines", style="section", positions=segments)


@feature_type(
    "loft",
    params=LoftParams,
    input=LoftInput,
    store=_store,
    reads=ReadSet(mesh=True),
)
class Loft:
    @staticmethod
    def references(params: LoftParams) -> Refs:
        return Refs(features=feature_refs(params.path), bodies=feature_refs(params.target_body))

    @staticmethod
    def evaluate(ctx: EvalContext, params: LoftParams) -> FeatureOutput:
        axis = loft_axis(params.path, ctx.construction)
        mesh = ctx.mesh
        faces = mesh.faces
        if params.faces is not None:
            subset = ctx.face_set(params.faces)
            faces = faces[subset[(subset >= 0) & (subset < len(faces))]]
        ctx.job.progress(None, ProgressStage.SECTIONING)
        with ctx.job.native(ProgressStage.LOFTING):
            loft = loft_scan(
                mesh.vertices,
                faces,
                axis,
                params.start,
                params.end,
                params.section_count,
                ctx.job.check_cancelled,
            )
        body = tagged_body(loft, ctx.feature_id)
        output = solid_output(ctx.feature_id, params.operation, params.target_body, body, ctx.body)
        stats: dict[str, float | None] = {
            "freeform.stats.sections": float(len(loft.sections)),
            "freeform.stats.sectionRms": loft.section_rms,
            "freeform.stats.sectionMax": loft.section_max,
        }
        return replace(output, display=(section_display(loft),), stats=stats)
