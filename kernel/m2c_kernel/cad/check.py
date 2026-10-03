"""Validity checks for solid bodies.

`BRepCheck_Analyzer.IsValid()` is necessary but not sufficient: a body must also
be exactly one solid with positive volume, and vertex tolerances far above the
modelling precision are an early sign of failing booleans and fillets later.
"""

from __future__ import annotations

from dataclasses import dataclass

from m2c_kernel.cad.occ_compat import (
    BRep_Tool,
    BRepCheck_Analyzer,
    TopAbs_EDGE,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopoDS,
    TopoDS_Shape,
    indexed_map,
)
from m2c_kernel.cad.properties import area, volume

HIGH_TOLERANCE_MM = 1e-4


@dataclass(frozen=True)
class SolidCheck:
    valid: bool
    solids: int
    volume: float
    area: float
    max_tolerance: float

    @property
    def is_usable(self) -> bool:
        """One valid solid with positive volume."""
        return self.valid and self.solids == 1 and self.volume > 0.0

    @property
    def high_tolerance(self) -> bool:
        return self.max_tolerance > HIGH_TOLERANCE_MM


def max_tolerance(shape: TopoDS_Shape) -> float:
    """Largest vertex or edge tolerance of the shape (mm)."""
    largest = 0.0
    vertices = indexed_map(shape, TopAbs_VERTEX)
    for index in range(1, vertices.Extent() + 1):
        largest = max(largest, BRep_Tool.Tolerance_s(TopoDS.Vertex(vertices.FindKey(index))))
    edges = indexed_map(shape, TopAbs_EDGE)
    for index in range(1, edges.Extent() + 1):
        largest = max(largest, BRep_Tool.Tolerance_s(TopoDS.Edge(edges.FindKey(index))))
    return float(largest)


def check_solid(shape: TopoDS_Shape) -> SolidCheck:
    if shape is None or shape.IsNull():
        return SolidCheck(valid=False, solids=0, volume=0.0, area=0.0, max_tolerance=0.0)
    return SolidCheck(
        valid=bool(BRepCheck_Analyzer(shape).IsValid()),
        solids=indexed_map(shape, TopAbs_SOLID).Extent(),
        volume=volume(shape),
        area=area(shape),
        max_tolerance=max_tolerance(shape),
    )
