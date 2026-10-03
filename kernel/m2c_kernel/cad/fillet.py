"""Constant-size fillets and symmetric chamfers on body edges.

New faces are tagged `<tag>:fillet:<n>` or `<tag>:chamfer:<n>`, where `n` is the
index of the edge reference that created them; tags of the other faces are
carried through the builder's history. Where the faces of an edge bend tighter
than a fillet's radius, the radius narrows there (`fillet_law.py`); the result
reports the smallest radius used. A failure is reported with the number
of faulty contours (`.work/research/algorithms-cad.md` 2.5): `IsDone() == False`
and `StdFail_NotDone` both count as failure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

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
    maker: Any = (
        BRepFilletAPI_MakeChamfer(body.shape) if chamfer else BRepFilletAPI_MakeFillet(body.shape)
    )
    laws = {} if chamfer else _laws(body.shape, edges, size)
    for index, edge in enumerate(edges):
        if index in laws:
            maker.Add(TopoDS.Edge(edge))
        else:
            maker.Add(size, TopoDS.Edge(edge))
    for index, law in laws.items():
        _set_law(maker, edges[index], law, size, [edges[other] for other in laws])
    details = None
    try:
        maker.Build()
        done = bool(maker.IsDone())
        shape = maker.Shape() if done else None
    except (StdFail_NotDone, Standard_Failure) as failure:
        done, shape, details = False, None, str(failure)
    if not done or shape is None:
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
    smallest = min((law.smallest for law in laws.values()), default=None)
    return Rounded(collector.body(), smallest)


def _laws(shape: TopoDS_Shape, edges: Sequence[TopoDS_Shape], size: float) -> dict[int, RadiusLaw]:
    """Radius laws of the edges that need one, by their index in `edges`."""
    edge_faces = EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)
    laws = {}
    for index, edge in enumerate(edges):
        if not edge_faces.Contains(edge):
            continue
        faces = list(edge_faces.FindFromKey(edge))
        if len(faces) != 2 or faces[0].IsSame(faces[1]):
            continue
        law = radius_law(edge, (faces[0], faces[1]), size)
        if law is not None:
            laws[index] = law
    return laws


def _set_law(
    maker: Any, edge: TopoDS_Shape, law: RadiusLaw, size: float, narrowing: list[TopoDS_Shape]
) -> None:
    """Give `edge` its radius law; edges of its contour without a law keep `size`."""
    contour = maker.Contour(TopoDS.Edge(edge))
    values = Array1_gp_Pnt2d(1, len(law.parameters))
    for index, (parameter, radius) in enumerate(zip(law.parameters, law.radii, strict=True), 1):
        values.SetValue(index, gp_Pnt2d(float(parameter), float(radius)))
    for position in range(1, maker.NbEdges(contour) + 1):
        other = maker.Edge(contour, position)
        if other.IsSame(edge):
            maker.SetRadius(values, contour, position)
        elif not any(other.IsSame(item) for item in narrowing):
            maker.SetRadius(size, contour, position)
