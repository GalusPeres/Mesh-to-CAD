"""Sketch: lines, arcs and circles on a plane, fitted to a section of the scan.

The stored entities are authoritative. A rebuild builds profile faces from them
and does not refit; if the plane moved (a refitted reference, a new alignment),
the entities move with it, and the sketch is compared with the current section:
above the project tolerance it carries `sketch.deviatesFromScan`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from m2c_kernel.codes.sketch import IssueCode
from m2c_kernel.document.results import DisplaySource, FeatureOutput, Issue
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue
from m2c_kernel.sketch.api import cut, deviation_from, evaluate, section_geometry
from m2c_kernel.sketch.params import (
    AxisNormalSource,
    FeaturePlaneSource,
    PlanarSection,
    SketchParams,
)
from m2c_kernel.sketch.section import to_xyz

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext, EvalMesh


def sketch_references(params: SketchParams) -> tuple[str, ...]:
    section = params.section
    if isinstance(section, PlanarSection):
        source = section.plane
        if isinstance(source, FeaturePlaneSource):
            return feature_refs(source.feature)
        if isinstance(source, AxisNormalSource):
            return feature_refs(source.axis)
        return ()
    return feature_refs(section.axis)


def _mesh(ctx: EvalContext) -> EvalMesh | None:
    try:
        return ctx.mesh
    except KernelError:
        return None


@feature_type("sketch", params=SketchParams, reads=ReadSet(mesh=True, settings=("tolerance",)))
class Sketch:
    @staticmethod
    def references(params: SketchParams) -> Refs:
        return Refs(features=sketch_references(params))

    @staticmethod
    def evaluate(ctx: EvalContext, params: SketchParams) -> FeatureOutput:
        geometry = section_geometry(params.section, ctx.construction)
        result = evaluate(params, geometry)
        issues: list[Issue] = []
        profile = result.profile
        if profile.open_entities:
            gaps: list[JsonValue] = [[float(v) for v in gap] for gap in result.gaps]
            issues.append(Issue(IssueCode.PROFILE_OPEN, {"count": len(gaps), "gaps": gaps}))
        for loop in result.invalid_loops:
            issues.append(Issue(IssueCode.PROFILE_INVALID, {"loop": loop}))

        display = [
            DisplaySource(
                kind="lines", style="sketch", positions=result.segments, ids=result.segment_entities
            )
        ]
        stats: dict[str, float | None] = {
            "sketch.entities": float(len(params.entities)),
            "sketch.loops": float(len(profile.loops)),
        }
        mesh = _mesh(ctx)
        if mesh is not None:
            section = cut(mesh.vertices, mesh.faces, geometry, mesh.vertex_normals)
            raw = section.raw_points()
            if len(raw):
                display.append(
                    DisplaySource(
                        kind="points", style="sectionPoints", positions=to_xyz(geometry.frame, raw)
                    )
                )
            worst = deviation_from(params, section)
            stats["sketch.deviation"] = worst
            if worst is None:
                issues.append(Issue(IssueCode.SECTION_EMPTY))
            elif worst > ctx.settings.tolerance:
                issues.append(Issue(IssueCode.DEVIATES_FROM_SCAN, {"max": round(worst, 6)}))
        return FeatureOutput(
            sketch=result.profiles,
            display=tuple(display),
            stats=stats,
            issues=tuple(issues),
        )
