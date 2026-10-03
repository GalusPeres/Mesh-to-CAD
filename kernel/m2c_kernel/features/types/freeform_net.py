"""Freeform net: a quad control net whose limit surface becomes B-spline CAD faces.

The net (control points and quads) is the stored, editable source of the feature; the
B-spline faces are derived from it on every rebuild (`surfacing/net.py`): one face per
rectangle of the net's patch layout. A closed net gives a solid body whose faces are
tagged `<id>:patch:<i>` (rectangle i of the layout).
A net with open borders (or in separate pieces, as while it is built by hand) gives
open faces, kept as construction geometry with the issue `surfacing.openNet`, because
bodies must be solids.

`faces` remembers the scan triangles the net was generated for. It is not needed to
build the shape; the tool uses it to fit the net again to the same part of the scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.cad.occ_compat import BRepCheck_Analyzer, TopAbs_FACE, indexed_map
from m2c_kernel.codes.surfacing import ErrorCode, IssueCode
from m2c_kernel.document.results import (
    Body,
    BodyUpdate,
    Construction,
    DisplaySource,
    FeatureOutput,
    Issue,
)
from m2c_kernel.features.registry import ReadSet, Refs, feature_type
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import BlobRef, F64Array, U32Array

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.session.blobs import BlobStore
    from m2c_kernel.surfacing.net import NetShape


@dataclass(frozen=True, kw_only=True)
class FreeformNetParams:
    vertices: BlobRef
    """Control points, float64 (n, 3), part coordinates."""
    quads: BlobRef
    """uint32 (q, 4), counter-clockwise seen from outside the material."""
    faces: BlobRef | None = None
    """Scan triangles the net was made for; None means the whole scan."""


@dataclass(frozen=True, kw_only=True)
class FreeformNetInput:
    """Like `FreeformNetParams`, but the arrays arrive as buffers."""

    vertices: F64Array
    quads: U32Array
    faces: U32Array | None = None


def _store(value: FreeformNetInput, blobs: BlobStore) -> FreeformNetParams:
    vertices = np.asarray(value.vertices, dtype=np.float64).reshape(-1, 3)
    quads = np.asarray(value.quads, dtype=np.uint32).reshape(-1, 4)
    faces = None if value.faces is None else blobs.put(np.unique(value.faces).astype(np.uint32))
    return FreeformNetParams(vertices=blobs.put(vertices), quads=blobs.put(quads), faces=faces)


def net_arrays(blobs: BlobStore, params: FreeformNetParams) -> tuple[np.ndarray, np.ndarray]:
    """Control points (n, 3) float64 and quads (q, 4) int64 of a stored net."""
    vertices = np.asarray(blobs.get(params.vertices), dtype=np.float64).reshape(-1, 3)
    quads = np.asarray(blobs.get(params.quads), dtype=np.int64).reshape(-1, 4)
    return vertices, quads


def net_stats(
    shape: NetShape, quads: int, deviation_points: np.ndarray | None
) -> dict[str, float | None]:
    """Feature statistics, read by the renderer's freeform-net view."""
    from m2c_kernel.surfacing.net import net_deviation

    deviation = None if deviation_points is None else net_deviation(shape, deviation_points)
    return {
        "patches": float(len(shape.faces)),
        "quads": float(quads),
        "closed": 1.0 if shape.closed else 0.0,
        "deviationRms": None if deviation is None else deviation.rms,
        "deviationMean": None if deviation is None else deviation.mean,
        "deviationP95": None if deviation is None else deviation.p95,
        "deviationMax": None if deviation is None else deviation.max,
    }


def _face_tags(feature_id: str, shape: NetShape) -> tuple[str, ...]:
    faces = indexed_map(shape.shape, TopAbs_FACE)
    tags = [""] * faces.Extent()
    for patch, face in enumerate(shape.faces):
        tags[faces.FindIndex(face) - 1] = f"{feature_id}:patch:{patch}"
    return tuple(tags)


def _shell_display(shape: NetShape) -> tuple[DisplaySource, ...]:
    from m2c_kernel.cad.tessellate import tessellate

    mesh = tessellate(shape.shape)
    return (
        DisplaySource(kind="mesh", style="patch", positions=mesh.vertices, indices=mesh.triangles),
        DisplaySource(kind="lines", style="constructionEdges", positions=mesh.edge_segments),
    )


@feature_type(
    "freeformNet",
    params=FreeformNetParams,
    input=FreeformNetInput,
    store=_store,
    reads=ReadSet(mesh=True),
)
class FreeformNet:
    @staticmethod
    def references(params: FreeformNetParams) -> Refs:
        return Refs()

    @staticmethod
    def evaluate(ctx: EvalContext, params: FreeformNetParams) -> FeatureOutput:
        from m2c_kernel.surfacing.net import NetError, net_shape

        vertices, quads = net_arrays(ctx.blobs, params)
        try:
            shape = net_shape(vertices, quads, ctx.job.check_cancelled)
        except NetError as error:
            raise KernelError(ErrorCode.NET_INVALID, details=str(error)) from error
        if not BRepCheck_Analyzer(shape.shape).IsValid():
            raise KernelError(ErrorCode.NET_SHAPE_INVALID)

        mesh = ctx.mesh
        measured = ~mesh.synthetic
        if params.faces is not None:
            selected = np.zeros(len(mesh.faces), dtype=bool)
            selected[ctx.face_set(params.faces)] = True
            measured &= selected
        points = mesh.vertices[np.unique(mesh.faces[measured])] if np.any(measured) else None
        stats = net_stats(shape, len(quads), points)

        if not shape.closed:
            return FeatureOutput(
                construction=Construction(surface=shape.shape),
                display=_shell_display(shape),
                stats=stats,
                issues=(Issue(IssueCode.OPEN_NET),),
            )
        body = Body(shape=shape.shape, face_tags=_face_tags(ctx.feature_id, shape))
        return FeatureOutput(bodies=BodyUpdate(changed={ctx.feature_id: body}), stats=stats)
