"""Features with an inclined top: extruded up to a plane fitted to their top.

The arms of a direction pad slope down towards its centre; a flat extrusion would stand
up to half a millimetre proud of the scan at one end. Each such feature gets a `fit`
plane through the scan triangles of its top and an extrusion of its outline up to that
plane, so it follows the scan and stays editable (the fit can be refitted, the outline
edited). Its sketch starts `OVERLAP_MM` behind the base plane like the other added and
cut extrusions; an extrusion up to a plane has no backward distance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.api import Feature
from m2c_kernel.recognition.build_rounding import TopEdges, top_edges
from m2c_kernel.recognition.chain import chain_distances
from m2c_kernel.recognition.contours import inside_contour
from m2c_kernel.recognition.planes import BasePlane
from m2c_kernel.recognition.relief import Relief
from m2c_kernel.recognition.sketch_ops import SketchDraft, as_list, chain_entities

type AddFeature = Callable[..., str]

TOP_MARGIN_MM = 0.5
"""Top triangles keep this far inside the outline, clear of the rounding."""
TOP_TOLERANCE_FACTOR = 4.0
MIN_TOP_TOLERANCE_MM = 0.08


def inclined_extrusion(
    add: AddFeature,
    plane: BasePlane,
    plane_id: str,
    shift: FloatArray,
    index: int,
    feature: Feature,
    top_faces: np.ndarray,
    target_body: str | None,
    name: str | None,
    overlap: float,
) -> TopEdges:
    """Fit plane, sketch and extrusion of one feature with an inclined top."""
    relief = feature.relief
    faces = np.asarray(top_faces, dtype=np.uint32)
    fit_id = add(
        "fit",
        {
            "faces": {"$buf": 0, "dtype": "uint32", "shape": [len(faces)]},
            "kind": "plane",
            "robust": True,
            "snap": False,
        },
        (faces,),
    )
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
        "extent": {"type": "toPlane", "feature": fit_id},
    }
    if target_body:
        params |= {"operation": "add" if relief.kind == "boss" else "cut"}
        params["targetBody"] = target_body
    else:
        params["operation"] = "newBody"
    extrusion = add("extrude", params, name=name)
    return top_edges(index, feature, plane, entities, target_body or extrusion, extrusion)


def top_faces(
    plane: BasePlane,
    relief: Relief,
    centroids: FloatArray,
    face_normals: FloatArray,
    noise: float,
) -> np.ndarray:
    """The scan triangles of an inclined top: inside the outline, on the top's plane."""
    uvh = plane.to_plane(centroids)
    finite = np.isfinite(uvh).all(axis=1)
    tolerance = max(TOP_TOLERANCE_FACTOR * noise, MIN_TOP_TOLERANCE_MM)
    near = np.zeros(len(uvh), dtype=bool)
    near[finite] = np.abs(uvh[finite, 2] - relief.top_at(uvh[finite, :2])) < tolerance
    candidates = np.flatnonzero(near)
    uv = uvh[candidates, :2]
    inside = inside_contour(uv, relief.contour) & (
        chain_distances(relief.outline.chain, uv) > TOP_MARGIN_MM
    )
    slope = np.array([-relief.slope[0], -relief.slope[1], 1.0])
    up = plane.from_plane(slope[None, :])[0] - plane.origin
    up /= np.linalg.norm(up)
    facing = face_normals[candidates] @ up > np.cos(np.radians(15.0))
    result: np.ndarray = candidates[inside & facing].astype(np.uint32)
    return result
