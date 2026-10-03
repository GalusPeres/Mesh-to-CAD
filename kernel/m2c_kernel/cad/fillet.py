"""Constant-size fillets and symmetric chamfers on body edges.

New faces are tagged `<tag>:fillet:<n>` or `<tag>:chamfer:<n>`, where `n` is the
index of the edge reference that created them; tags of the other faces are
carried through the builder's history. When a fillet fails, it is tried once more
with a radius that narrows where the faces bend tighter than it (`fillet_law.py`);
the result then reports the smallest radius used. Only then: on analytic faces Open
CASCADE often manages the constant radius where the narrowing one fails. A failure
is reported with the number of faulty contours (`.work/research/algorithms-cad.md`
2.5): `IsDone() == False` and `StdFail_NotDone` both count as failure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from m2c_kernel.cad.check import max_tolerance
from m2c_kernel.cad.fillet_law import RadiusLaw, radius_law
from m2c_kernel.cad.occ_compat import (
    Array1_gp_Pnt2d,
    BRepFilletAPI_MakeChamfer,
    BRepFilletAPI_MakeFillet,
    EdgeFaceMap,
    Standard_Failure,
    StdFail_NotDone,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopExp,
    TopoDS,
    TopoDS_Shape,
    gp_Pnt2d,
)
from m2c_kernel.cad.tags import TagCollector
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.errors import KernelError

type EdgeMode = Literal["fillet", "chamfer"]

MAX_TOLERANCE_MM = 0.01
"""A result with an edge or vertex looser than this failed (good ones: about 1e-4 mm)."""


@dataclass(frozen=True)
class Rounded:
    body: Body
    smallest: float | None = None
    """The smallest radius where a fillet had to narrow; None where it kept its size."""


def fillet_edges(
    body: Body, edges: Sequence[TopoDS_Shape], size: float, mode: EdgeMode, tag: str
) -> Rounded:
    if not edges:
        raise KernelError(ErrorCode.NO_EDGES)
    chamfer = mode == "chamfer"
    failure_code = ErrorCode.CHAMFER_FAILED if chamfer else ErrorCode.FILLET_FAILED
    maker, shape, details, laws = _build(body, edges, size, chamfer, narrow=False)
    if shape is None and not chamfer:
        narrowing, narrowed, _, narrowing_laws = _build(body, edges, size, chamfer, narrow=True)
        if narrowed is not None and narrowing_laws:
            maker, shape, laws = narrowing, narrowed, narrowing_laws
    if shape is None:
        contours = 0 if chamfer else int(maker.NbFaultyContours())
        raise KernelError(failure_code, {"size": size, "contours": contours}, details)
    collector = TagCollector(shape)
    collector.carry(maker, body)
    for index, edge in enumerate(edges):
        collector.set_all(maker.Generated(edge), f"{tag}:{mode}:{index}")
    collector.fill_by_proximity([body])
    for index in collector.missing():
        # Corner patches where several rounded edges meet belong to the rounding.
        collector.set(collector.face(index), f"{tag}:{mode}:corner")
    smallest = min((law.smallest for law in laws), default=None)
    return Rounded(collector.body(), smallest)


def _build(
    body: Body, edges: Sequence[TopoDS_Shape], size: float, chamfer: bool, *, narrow: bool
) -> tuple[Any, TopoDS_Shape | None, str | None, list[RadiusLaw]]:
    """The builder, its result (None where it failed), the reason and the radius laws."""
    maker: Any = (
        BRepFilletAPI_MakeChamfer(body.shape) if chamfer else BRepFilletAPI_MakeFillet(body.shape)
    )
    for edge in edges:
        maker.Add(size, TopoDS.Edge(edge))
    laws = _narrow(maker, body.shape, size) if narrow else []
    try:
        maker.Build()
        shape = maker.Shape() if maker.IsDone() else None
    except (StdFail_NotDone, Standard_Failure) as failure:
        return maker, None, str(failure), laws
    if shape is not None and max_tolerance(shape) > MAX_TOLERANCE_MM:
        # Open CASCADE calls it done, but a patch did not close: on a remote control's
        # back edge the rounding fell apart into 80 faces around a 1.1 mm gap.
        return maker, None, f"tolerance {max_tolerance(shape):.3g} mm", laws
    return maker, shape, None, laws


def _narrow(maker: Any, shape: TopoDS_Shape, size: float) -> list[RadiusLaw]:
    """Radius laws for every edge of every contour that bends tighter than `size`.

    A contour also runs along the tangent neighbours of the picked edges, so each of
    its edges is checked, not only the picked ones.
    """
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    laws = []
    for contour in range(1, maker.NbContours() + 1):
        for position in range(1, maker.NbEdges(contour) + 1):
            edge = maker.Edge(contour, position)
            faces = list(edge_faces.FindFromKey(edge)) if edge_faces.Contains(edge) else []
            if len(faces) != 2 or faces[0].IsSame(faces[1]):
                continue
            law = radius_law(edge, (faces[0], faces[1]), size)
            if law is None:
                continue
            values = Array1_gp_Pnt2d(1, len(law.parameters))
            for index, (parameter, radius) in enumerate(
                zip(law.parameters, law.radii, strict=True), 1
            ):
                values.SetValue(index, gp_Pnt2d(float(parameter), float(radius)))
            maker.SetRadius(values, contour, position)
            laws.append(law)
    return laws
