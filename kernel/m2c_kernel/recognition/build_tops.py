"""Features whose top is not flat: built up to their own top, fitted to the scan.

A flat extrusion would stand proud of an inclined or domed top by up to half a
millimetre at one end. Each such feature gets its own sketch and

- for a plane (an inclined top): a `fit` plane through the scan triangles of its top
  and an extrusion up to that plane;
- for a curved top (a direction pad's arm lies on a cone around the pad's axis, a
  button may be domed): a `freeformPatch` fitted to those triangles, an extrusion as a
  body of its own past the top, a `trim` that keeps what lies below the patch, and,
  with a target body, a `combine` that adds it.

Everything stays editable: the fit can be refitted, the outline edited. Sketches start
`overlap` behind the base plane like the other added and cut extrusions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature
from m2c_kernel.recognition.build_rounding import TopEdges, top_edges
from m2c_kernel.recognition.chain import chain_distances, chain_points
from m2c_kernel.recognition.contours import inside_contour
from m2c_kernel.recognition.planes import BasePlane
from m2c_kernel.recognition.relief import Relief
from m2c_kernel.recognition.sketch_ops import SketchDraft, as_list, chain_entities

type AddFeature = Callable[..., str]

PLANE_MARGIN_MM = 0.5
"""Triangles of a plane top keep this far inside the outline, clear of the rounding."""
PATCH_MARGIN_MM = 1.0
"""Triangles of a curved top keep farther inside: the rounding would bend the patch."""
PATCH_REACH_MM = 1.5
"""The patch reaches this far past the outline, so it cuts through the whole wall."""
PATCH_SPANS = 3
ABOVE_MM = 0.5
TOP_TOLERANCE_FACTOR = 4.0
MIN_TOP_TOLERANCE_MM = 0.08


def own_top(feature: Feature) -> bool:
    """Whether the feature is built up to its own top surface instead of a height."""
    relief = feature.relief
    if relief.top_surface is None or relief.top not in ("inclined", "domed"):
        return False
    # A pocket's curved floor would need the patch the other way round; it stays flat.
    return relief.kind == "boss" or relief.top_surface.planar


def top_extrusion(
    add: AddFeature,
    plane: BasePlane,
    plane_id: str,
    shift: FloatArray,
    index: int,
    feature: Feature,
    faces_of_top: Callable[[float], np.ndarray],
    target_body: str | None,
    name: str | None,
    overlap: float,
) -> TopEdges:
    """The features that build one feature up to its own top; where its top edges are.

    `faces_of_top(margin)` gives the scan triangles of the top, `margin` inside the outline.
    """
    relief = feature.relief
    assert relief.top_surface is not None
    planar = relief.top_surface.planar
    faces = np.asarray(faces_of_top(PLANE_MARGIN_MM if planar else PATCH_MARGIN_MM), np.uint32)
    buffer = {"$buf": 0, "dtype": "uint32", "shape": [len(faces)]}
    if planar:
        top = add(
            "fit", {"faces": buffer, "kind": "plane", "robust": True, "snap": False}, (faces,)
        )
    else:
        reach = PATCH_MARGIN_MM + PATCH_REACH_MM
        # Few spans: the top is smooth, and more would follow the scan's noise.
        spans = [PATCH_SPANS, PATCH_SPANS]
        top = add("freeformPatch", {"faces": buffer, "margin": reach, "spans": spans}, (faces,))
    sketch = SketchDraft()
    entities = chain_entities(sketch, feature.outline.chain, shift)
    sign = 1.0 if relief.kind == "boss" else -1.0
    behind = overlap if target_body else 0.0
    sketch_id = add(
        "sketch",
        {
            "section": {
                "type": "planar",
                "plane": {"type": "feature", "feature": plane_id},
                "offset": relief.level - sign * behind,
                "sectionOffset": sign * (behind + relief.height / 2.0),
                "xDirection": as_list(plane.x_axis),
            },
            "points": sketch.points,
            "entities": sketch.entities,
            "constraints": sketch.constraints,
        },
    )
    params: dict[str, Any] = {
        "sketch": sketch_id,
        "loops": [entities[0]],
        "direction": "normal" if relief.kind == "boss" else "reversed",
    }
    if planar:
        params["extent"] = {"type": "toPlane", "feature": top}
        if target_body:
            params |= {"operation": "add" if relief.kind == "boss" else "cut"}
            params["targetBody"] = target_body
        extrusion = add("extrude", params, name=name)
        return top_edges(index, feature, plane, entities, target_body or extrusion, extrusion)
    # Curved: a body of its own past the top, cut by the patch, added to the target.
    highest = float(relief.top_at(chain_points(feature.outline.chain)).max()) - relief.level
    params["extent"] = {"type": "distance", "forward": behind + highest + ABOVE_MM}
    extrusion = add("extrude", params, name=name)
    add("trim", {"targetBody": extrusion, "tool": {"type": "patch", "feature": top}})
    if target_body:
        add("combine", {"targetBody": target_body, "tools": [extrusion], "operation": "add"})
    return top_edges(index, feature, plane, entities, target_body or extrusion, extrusion)


def top_faces(
    plane: BasePlane,
    relief: Relief,
    centroids: FloatArray,
    face_normals: FloatArray,
    noise: float,
    margin: float,
) -> np.ndarray:
    """The scan triangles of a top: inside the outline by `margin`, on its surface."""
    uvh = plane.to_plane(centroids)
    finite = np.isfinite(uvh).all(axis=1)
    tolerance = max(TOP_TOLERANCE_FACTOR * noise, MIN_TOP_TOLERANCE_MM)
    near = np.zeros(len(uvh), dtype=bool)
    near[finite] = np.abs(uvh[finite, 2] - relief.top_at(uvh[finite, :2])) < tolerance
    candidates = np.flatnonzero(near)
    uv = uvh[candidates, :2]
    inside = inside_contour(uv, relief.contour) & (
        chain_distances(relief.outline.chain, uv) > margin
    )
    rise = relief.top_gradient(uv)
    up_local = np.column_stack([-rise, np.ones(len(uv))])
    up_local /= np.linalg.norm(up_local, axis=1, keepdims=True)
    axes = np.column_stack([plane.x_axis, plane.y_axis, plane.normal])
    facing = np.einsum("ij,ij->i", face_normals[candidates], up_local @ axes.T)
    result: np.ndarray = candidates[inside & (facing > np.cos(np.radians(15.0)))].astype(np.uint32)
    return result
