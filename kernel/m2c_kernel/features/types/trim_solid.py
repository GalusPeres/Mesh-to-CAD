"""Trim to a solid ("Zuschneiden", QuickSurface's Trim).

Bodies, open surfaces (freeform nets and patches) and planes cut each other into
pieces; the kept pieces become one body.

Which pieces are kept: by default those inside the scan (generalised winding number at
points inside each piece; without a scan the largest piece). `pieces` overrides that
per piece: each choice names the piece nearest to its point (a point the user clicked
on the piece), later choices win. When two pieces are equally near (a shared face),
the one the choice changes is meant.

The result keeps the id of the first body (the others are used up); without bodies it
is a new body with the feature's id. Pieces that are not kept are drawn as ghosts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.cad.booleans import fuse_all
from m2c_kernel.cad.cells import Cell, PlaneInput, SurfaceInput, distance_to, split_cells
from m2c_kernel.cad.occ_compat import TopoDS_Shape
from m2c_kernel.cad.references import reference_plane
from m2c_kernel.cad.trim import patch_face
from m2c_kernel.codes.cad import ErrorCode, ProgressStage
from m2c_kernel.document.results import BodyUpdate, DisplaySource, FeatureOutput
from m2c_kernel.features.common import feature_refs
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.geometry import Vec3
from m2c_kernel.protocol.errors import KernelError

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext

INSIDE_SCAN = 0.5
"""Winding number above which a point counts as inside the scan."""
_TIE_MM = 1e-4


@dataclass(frozen=True, kw_only=True)
class PieceChoice:
    point: Vec3
    """A point on (or in) the piece, part coordinates."""
    keep: bool


@dataclass(frozen=True, kw_only=True)
class TrimSolidParams:
    bodies: list[str]
    """Bodies to cut; the result keeps the first one's id, the others are used up."""
    surfaces: list[str]
    """Freeform nets or patches whose open surfaces cut."""
    planes: list[str]
    """Plane features or origin planes (`XY`, `YZ`, `XZ`)."""
    pieces: list[PieceChoice]


@feature_type("trimSolid", params=TrimSolidParams, reads=ReadSet(mesh=True))
class TrimSolid:
    @staticmethod
    def references(params: TrimSolidParams) -> Refs:
        return Refs(
            features=feature_refs(*params.surfaces, *params.planes),
            bodies=feature_refs(*params.bodies),
        )

    @staticmethod
    def evaluate(ctx: EvalContext, params: TrimSolidParams) -> FeatureOutput:
        bodies = list(dict.fromkeys(params.bodies))
        surfaces = [_surface(ctx, feature) for feature in dict.fromkeys(params.surfaces)]
        if not bodies and not surfaces:
            raise KernelError(ErrorCode.TRIM_NEEDS_SURFACE)
        planes = [
            PlaneInput(*reference_plane(plane, ctx.construction), tag=plane)
            for plane in dict.fromkeys(params.planes)
        ]
        with ctx.job.native(ProgressStage.BOOLEAN):
            inputs = [ctx.body(body) for body in bodies]
            cells = split_cells(inputs, surfaces, planes, ctx.feature_id)
        if not cells:
            raise KernelError(ErrorCode.NO_CLOSED_REGION)
        keep = _choose(cells, _default_keep(ctx, cells), params.pieces)
        kept = [cell.body for cell, chosen in zip(cells, keep, strict=True) if chosen]
        if not kept:
            raise KernelError(ErrorCode.NO_PIECE_KEPT)
        with ctx.job.native(ProgressStage.BOOLEAN):
            body = fuse_all(kept)
        target = bodies[0] if bodies else ctx.feature_id
        ghosts = [cell for cell, chosen in zip(cells, keep, strict=True) if not chosen]
        return FeatureOutput(
            bodies=BodyUpdate(changed={target: body}, removed=tuple(bodies[1:])),
            display=tuple(_ghost(cell) for cell in ghosts),
            stats={"pieces": float(len(cells)), "kept": float(len(kept))},
        )


def _surface(ctx: EvalContext, feature: str) -> SurfaceInput:
    surface = ctx.construction(feature).surface
    if surface is None:
        raise KernelError(ErrorCode.NOT_A_PATCH, {"feature": feature})
    shape = surface if isinstance(surface, TopoDS_Shape) else patch_face(surface)
    return SurfaceInput(shape, feature)


def _default_keep(ctx: EvalContext, cells: list[Cell]) -> list[bool]:
    """Pieces inside the scan; without a scan (or none inside) the largest piece."""
    try:
        mesh = ctx.mesh
    except KernelError:
        mesh = None
    keep = [False] * len(cells)
    if mesh is not None:
        from m2c_kernel.mesh.winding import winding_numbers

        for index, cell in enumerate(cells):
            if len(cell.probes) == 0:
                continue
            winding = np.abs(winding_numbers(mesh.vertices, mesh.faces, cell.probes[:2]))
            keep[index] = bool(winding.mean() > INSIDE_SCAN)
    if not any(keep):
        keep[int(np.argmax([cell.volume for cell in cells]))] = True
    return keep


def _choose(cells: list[Cell], keep: list[bool], choices: list[PieceChoice]) -> list[bool]:
    """Apply the user's choices in order; each one names the piece nearest to its point."""
    keep = list(keep)
    for choice in choices:
        point = np.asarray(choice.point, dtype=np.float64)
        distances = np.array([distance_to(cell.body.shape, point) for cell in cells])
        nearest = np.flatnonzero(distances <= distances.min() + _TIE_MM)
        changed = [index for index in nearest if keep[index] != choice.keep]
        keep[int(changed[0] if changed else nearest[0])] = choice.keep
    return keep


def _ghost(cell: Cell) -> DisplaySource:
    from m2c_kernel.cad.tessellate import tessellate

    mesh = tessellate(cell.body.shape)
    return DisplaySource(
        kind="mesh", style="construction", positions=mesh.vertices, indices=mesh.triangles
    )
