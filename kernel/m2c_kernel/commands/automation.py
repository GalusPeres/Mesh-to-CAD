"""Scan queries for automation clients (the MCP server in tools/mcp).

A person selects triangles with the mouse; an automation client describes them
geometrically instead: the triangles whose centroids lie in a box, optionally
only those facing a direction (the top of a part, one side wall). The result is
a face selection like the renderer's, usable as `faces` of a fit or a region.
Positions are part coordinates (after the alignment), in millimetres.

`automation.scanVertices` hands out the scan's vertices themselves, in the order of
the deviation map's values, so a client can sort the deviation into regions of its
own (the remote pipeline in tools/usertest/remote).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import numpy as np

from m2c_kernel.codes.regions import ErrorCode
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.geometry import Vec3, unit
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, Range, U32Array
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class FacesInBoxParams:
    min: Vec3
    max: Vec3
    facing: Vec3 | None = None
    """Keep only triangles whose normal lies within `max_angle_deg` of this direction."""
    max_angle_deg: Annotated[float, Range(0.0, 180.0)] = 30.0


@dataclass(frozen=True)
class FacesInBoxResult:
    faces: U32Array
    count: int


@dataclass(frozen=True)
class BoundsParams:
    pass


@dataclass(frozen=True)
class BoundsResult:
    min: Vec3
    max: Vec3
    faces: int


@dataclass(frozen=True)
class ScanVerticesParams:
    every: Annotated[int, Range(1, None)] = 1
    """Every n-th vertex, to keep the answer short; the indices are 0, n, 2n, ..."""


@dataclass(frozen=True)
class ScanVerticesResult:
    positions: F32Array
    """(k, 3) vertices in part coordinates, flat."""
    normals: F32Array
    """(k, 3) unit vertex normals, flat."""
    count: int
    """Vertices of the whole scan (the length of a deviation map)."""
    every: int


def _current_mesh(ctx: JobContext) -> EvalMesh:
    if ctx.session.document.scan is None:
        raise KernelError(ErrorCode.NO_SCAN)
    mesh = ctx.session.built(ctx).result.mesh
    if mesh is None:
        raise KernelError(ErrorCode.NO_SCAN)
    return mesh


def _vec3(values: np.ndarray) -> Vec3:
    return (float(values[0]), float(values[1]), float(values[2]))


@command("automation.facesInBox")
def faces_in_box(ctx: JobContext, params: FacesInBoxParams) -> FacesInBoxResult:
    """Triangles of the aligned scan with their centroid inside the box."""
    mesh = _current_mesh(ctx)
    low = np.minimum(params.min, params.max)
    high = np.maximum(params.min, params.max)
    centroids = mesh.face_centroids
    inside = np.all((centroids >= low) & (centroids <= high), axis=1)
    if params.facing is not None:
        direction = unit(params.facing)
        cosine = mesh.face_normals @ direction
        inside &= cosine >= np.cos(np.radians(params.max_angle_deg))
    faces = np.flatnonzero(inside).astype(np.uint32)
    return FacesInBoxResult(faces=faces, count=len(faces))


@command("automation.bounds")
def bounds(ctx: JobContext, params: BoundsParams) -> BoundsResult:
    """Bounding box of the aligned scan, to choose boxes for `automation.facesInBox`."""
    mesh = _current_mesh(ctx)
    return BoundsResult(
        min=_vec3(mesh.vertices.min(axis=0)),
        max=_vec3(mesh.vertices.max(axis=0)),
        faces=len(mesh.faces),
    )


@command("automation.scanVertices")
def scan_vertices(ctx: JobContext, params: ScanVerticesParams) -> ScanVerticesResult:
    """Every n-th vertex of the aligned scan with its normal, in deviation-map order."""
    mesh = _current_mesh(ctx)
    rows = slice(None, None, params.every)
    return ScanVerticesResult(
        positions=mesh.vertices[rows].astype(np.float32).ravel(),
        normals=mesh.vertex_normals[rows].astype(np.float32).ravel(),
        count=len(mesh.vertices),
        every=params.every,
    )
