"""Roundings measured from the scan.

`fillet.scanRadius` measures the radius of the rounding the scan shows at edges of a
body: cross-sections along the edges, a line-arc-line corner tangent to both faces
fitted in each (`fitting/corner.py`), the median over the sections, snapped to a
design value where one lies within its uncertainty. It works on short button edges
and on long edges that run around a whole outline. The fillet tool's _Radius aus
Scan_ and recognition use it; automation clients call it before adding a fillet.
"""

from __future__ import annotations

from dataclasses import dataclass

from m2c_kernel.cad.edge_frames import edge_frames
from m2c_kernel.cad.edges import resolve_edges
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.codes.document import ErrorCode as DocumentError
from m2c_kernel.document.model import Document
from m2c_kernel.document.rebuild import RebuildResult
from m2c_kernel.document.results import Body
from m2c_kernel.features.types.fillet import EdgeRef
from m2c_kernel.fitting.corner import edge_radius
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.snapping import snap_length

DEFAULT_NOISE_MM = 0.03


@dataclass(frozen=True, kw_only=True)
class ScanRadiusParams:
    target_body: str
    edges: list[EdgeRef]
    """The edges to measure, as the fillet feature references them."""
    before: str | None = None
    """Measure the body as it is before this feature (the fillet being edited)."""


@dataclass(frozen=True)
class ScanRadiusResult:
    radius: float
    """The design value (mm): the measured radius snapped where a value fits; 0 is sharp."""
    measured: float
    """Median radius of the sections (mm)."""
    rms: float
    """RMS distance of the scan points to the rounded corners (mm)."""
    samples: int
    """Cross-sections that measured the rounding."""
    spread: tuple[float, float]
    """10th and 90th percentile of the sections' radii (mm)."""


@command("fillet.scanRadius", lane=True)
def fillet_scan_radius(ctx: JobContext, params: ScanRadiusParams) -> ScanRadiusResult:
    """Measure the rounding of body edges from the scan."""
    built = ctx.session.built(ctx)
    document = built.document
    mesh = built.result.mesh
    if document.scan is None or mesh is None:
        raise KernelError(DocumentError.NO_SCAN)
    body = _body(built.result, document, params.target_body, params.before)
    if body is None:
        raise KernelError(DocumentError.UNKNOWN_FEATURE, {"feature": params.target_body})
    if not params.edges:
        raise KernelError(ErrorCode.NO_EDGES)
    edges = resolve_edges(body, [(edge.faces, edge.point) for edge in params.edges])
    frames = edge_frames(body.shape, edges)
    ctx.check_cancelled()
    noise = document.settings.noise_override or document.scan.noise or DEFAULT_NOISE_MM
    measured = edge_radius(mesh.vertices, mesh.vertex_tree, frames, noise)
    if measured is None:
        raise KernelError(ErrorCode.NO_SCAN_AT_EDGES, {"count": len(params.edges)})
    snap = snap_length(measured.radius, measured.uncertainty, units=document.settings.snap_units)
    return ScanRadiusResult(
        radius=snap.value if snap is not None and measured.radius > 0.0 else measured.radius,
        measured=measured.radius,
        rms=measured.rms,
        samples=measured.samples,
        spread=measured.spread,
    )


def _body(
    result: RebuildResult, document: Document, body_id: str, before: str | None
) -> Body | None:
    """The body at the end of the history, or as the last feature before `before` left it."""
    if before is None:
        return result.bodies.get(body_id)
    found = None
    for feature in document.features:
        if feature.id == before:
            break
        output = result.outputs.get(feature.id)
        if output is not None and body_id in output.bodies.changed:
            found = output.bodies.changed[body_id]
    return found
