"""Constant-size fillets and symmetric chamfers on body edges.

New faces are tagged `<tag>:fillet:<n>` or `<tag>:chamfer:<n>`, where `n` is the
index of the edge reference that created them; tags of the other faces are
carried through the builder's history. A failure is reported with the number
of faulty contours (`.work/research/algorithms-cad.md` 2.5): `IsDone() == False`
and `StdFail_NotDone` both count as failure.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from m2c_kernel.cad.occ_compat import (
    BRepFilletAPI_MakeChamfer,
    BRepFilletAPI_MakeFillet,
    Standard_Failure,
    StdFail_NotDone,
    TopoDS,
    TopoDS_Shape,
)
from m2c_kernel.cad.tags import TagCollector
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body
from m2c_kernel.protocol.errors import KernelError

type EdgeMode = Literal["fillet", "chamfer"]


def fillet_edges(
    body: Body, edges: Sequence[TopoDS_Shape], size: float, mode: EdgeMode, tag: str
) -> Body:
    if not edges:
        raise KernelError(ErrorCode.NO_EDGES)
    chamfer = mode == "chamfer"
    failure_code = ErrorCode.CHAMFER_FAILED if chamfer else ErrorCode.FILLET_FAILED
    maker: Any = (
        BRepFilletAPI_MakeChamfer(body.shape) if chamfer else BRepFilletAPI_MakeFillet(body.shape)
    )
    for edge in edges:
        maker.Add(size, TopoDS.Edge(edge))
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
    return collector.body()
