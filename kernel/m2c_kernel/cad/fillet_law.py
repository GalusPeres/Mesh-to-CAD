"""The radius of a fillet along an edge where its faces bend tighter than the radius.

A rolling ball of radius r touches each face at d = r / tan(theta/2) from the edge,
theta being the angle between the faces (90 degrees: d = r). Where the edge curves
towards the inside of a face with a radius of curvature below d, the contact line on
that face folds over itself and Open CASCADE cannot build the fillet. On a scanned
part this happens where a lofted wall turns a corner tighter than the rounding along
its end (a remote control: 0.3 mm corners under a 0.78 mm rounding).

A moulded part's rounding gets smaller in such a corner, and so does this one: the
radius follows min(r, SHARE * R * tan(theta/2)) and changes by at most SLOPE mm per mm
along the edge, so the rounding narrows and widens smoothly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepAdaptor_Curve,
    BRepAdaptor_Curve2d,
    BRepAdaptor_Surface,
    GCPnts_AbscissaPoint,
    TopAbs_EDGE,
    TopAbs_REVERSED,
    TopExp_Explorer,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt,
    gp_Pnt2d,
    gp_Vec,
)
from m2c_kernel.geometry import FloatArray

SHARE = 0.5
"""The radius stays this far below the tightest one the faces allow."""
SLOPE = 0.2
"""Largest change of the radius per mm along the edge."""
SAMPLE_MM = 0.1
"""Spacing of the samples along the edge. A lofted corner of 0.1 mm radius is 0.16 mm
long; coarser samples miss its peak, and the fillet fails there.

On the remote control's 330 mm button-face edge, radii of 0.3 to 1.5 mm all build
with these values (under a second); at SHARE 0.8 or SLOPE 0.5 they fail, and samples
every 0.05 mm make the same fillet take 26 s."""
MIN_SAMPLES = 64
MAX_SAMPLES = 20000


@dataclass(frozen=True)
class RadiusLaw:
    """Radius at edge parameters, ascending, from the first to the last parameter."""

    parameters: FloatArray
    radii: FloatArray

    @property
    def smallest(self) -> float:
        return float(self.radii.min())


def radius_law(
    edge: TopoDS_Shape, faces: tuple[TopoDS_Shape, TopoDS_Shape], radius: float
) -> RadiusLaw | None:
    """The radius along `edge` between `faces`; None where `radius` fits all along it."""
    typed = TopoDS.Edge(edge)
    curve = BRepAdaptor_Curve(typed)
    first, last = curve.FirstParameter(), curve.LastParameter()
    length = GCPnts_AbscissaPoint.Length_s(curve)
    count = min(max(math.ceil(length / SAMPLE_MM), MIN_SAMPLES), MAX_SAMPLES)
    closed = BRep_Tool.IsClosed_s(typed)
    parameters = np.linspace(first, last, count, endpoint=not closed)
    points, tangents, bending = _frames(curve, parameters)
    inward = [_inward(typed, face, parameters, tangents) for face in faces]
    if any(direction is None for direction in inward):
        return None
    first_in, second_in = (direction for direction in inward if direction is not None)
    # Distance of the contact lines from the edge per unit of radius: 1 / tan(theta/2).
    cosine = np.clip(np.einsum("ij,ij->i", first_in, second_in), -0.999, 0.999)
    contact = 1.0 / np.tan(np.arccos(cosine) / 2.0)
    folding = np.maximum(
        np.einsum("ij,ij->i", bending, first_in), np.einsum("ij,ij->i", bending, second_in)
    )
    allowed = np.where(folding > 1e-9, SHARE / (np.maximum(folding, 1e-9) * contact), np.inf)
    if allowed.min() >= radius:
        return None
    radii = _slope_limited(np.minimum(allowed, radius), points, closed)
    if closed:
        parameters = np.append(parameters, last)
        radii = np.append(radii, radii[0])
    return RadiusLaw(parameters, radii)


def _frames(
    curve: BRepAdaptor_Curve, parameters: FloatArray
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Points, unit tangents and curvature vectors (towards the centre, length 1/R)."""
    points, tangents, bending = [], [], []
    for parameter in parameters:
        point, first, second = gp_Pnt(), gp_Vec(), gp_Vec()
        curve.D2(float(parameter), point, first, second)
        d1 = np.array([first.X(), first.Y(), first.Z()])
        d2 = np.array([second.X(), second.Y(), second.Z()])
        speed = float(np.linalg.norm(d1))
        tangent = d1 / speed
        points.append([point.X(), point.Y(), point.Z()])
        tangents.append(tangent)
        bending.append((d2 - (d2 @ tangent) * tangent) / speed**2)
    return np.array(points), np.array(tangents), np.array(bending)


def _inward(
    edge: TopoDS_Shape, face: TopoDS_Shape, parameters: FloatArray, tangents: FloatArray
) -> FloatArray | None:
    """Unit directions into `face`, across the edge, at each parameter.

    Seen against the face's outward normal, a face lies to the left of its boundary
    edges as they run in the face's orientation: inside = normal x tangent.
    """
    typed = TopoDS.Face(face)
    orientation = _orientation_in(edge, typed)
    if orientation is None:
        return None
    surface = BRepAdaptor_Surface(typed)
    pcurve = BRepAdaptor_Curve2d(TopoDS.Edge(edge), typed)
    flip = (typed.Orientation() == TopAbs_REVERSED) != (orientation == TopAbs_REVERSED)
    result = []
    for parameter, tangent in zip(parameters, tangents, strict=True):
        uv = pcurve.Value(float(parameter))
        normal = _normal(surface, uv)
        inside = np.cross(normal, tangent)
        result.append(-inside if flip else inside)
    directions = np.array(result)
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    unit_directions: FloatArray = directions / np.maximum(norms, 1e-12)
    return unit_directions


def _normal(surface: BRepAdaptor_Surface, uv: gp_Pnt2d) -> FloatArray:
    point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surface.D1(uv.X(), uv.Y(), point, du, dv)
    normal = du.Crossed(dv)
    return np.array([normal.X(), normal.Y(), normal.Z()])


def _orientation_in(edge: TopoDS_Shape, face: TopoDS_Shape) -> object | None:
    """The orientation of `edge` in the boundary of `face`; None for a seam or no match."""
    found = []
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    while explorer.More():
        if explorer.Current().IsSame(edge):
            found.append(explorer.Current().Orientation())
        explorer.Next()
    return found[0] if len(found) == 1 else None


def _slope_limited(limit: FloatArray, points: FloatArray, closed: bool) -> FloatArray:
    """The largest radii not above `limit` that change by at most SLOPE per mm.

    Two sweeps along the edge; around a closed edge each sweep runs twice, so a small
    radius near the start also narrows the end.
    """
    count = len(limit)
    ahead = np.roll(points, -1, axis=0) if closed else np.vstack([points[1:], points[-1:]])
    gaps = np.linalg.norm(ahead - points, axis=1)  # from each sample to the next
    span = 2 * count if closed else count
    radii = limit.copy()
    for index in range(1, span):
        here, before = index % count, (index - 1) % count
        radii[here] = min(radii[here], radii[before] + SLOPE * gaps[before])
    for index in range(span - 2, -1, -1):
        here, after = index % count, (index + 1) % count
        radii[here] = min(radii[here], radii[after] + SLOPE * gaps[here])
    return radii
