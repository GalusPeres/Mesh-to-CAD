"""Solid operations for the modelling features.

Not implemented yet. Every operation returns a `Body` whose faces carry tags
(see `m2c_kernel.document.results`), and every result is checked with
`cad.check.check_solid`. Booleans follow the policy in ARCHITECTURE.md 4.11:
snap near-coincident geometry first, fuzzy value 1e-5 mm, non-destructive,
history on. Methods and measurements: `.work/research/algorithms-cad.md` section 2.
"""

from __future__ import annotations

from typing import Any, Literal

from m2c_kernel.document.results import Body, PlaneFrame
from m2c_kernel.geometry import Vec3


def extrude(faces: list[Any], frame: PlaneFrame, forward: float, backward: float, tag: str) -> Body:
    """Extrude planar faces along the frame normal."""
    raise NotImplementedError("extrude")


def revolve(
    faces: list[Any], axis_point: Vec3, axis_direction: Vec3, angle_deg: float, tag: str
) -> Body:
    """Revolve planar faces about an axis in their plane."""
    raise NotImplementedError("revolve")


def combine(target: Body, tools: list[Body], operation: Literal["add", "cut", "intersect"]) -> Body:
    """Boolean operation with face-tag propagation through the operation history."""
    raise NotImplementedError("boolean operations")


def fillet_edges(body: Body, edges: list[Any], size: float, chamfer: bool, tag: str) -> Body:
    """Constant-radius fillet or symmetric chamfer on the given edges."""
    raise NotImplementedError("fillet and chamfer")
