"""Sketches under construction for recognised features (the JSON form of `sketch`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from m2c_kernel.geometry import FloatArray
from m2c_kernel.recognition.chain import Chain


@dataclass
class SketchDraft:
    """Points, entities and constraints of one sketch under construction (JSON form)."""

    points: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    counter: int = 0

    def point(self, xy: FloatArray) -> str:
        self.counter += 1
        pid = f"p{self.counter}"
        self.points.append({"id": pid, "x": float(xy[0]), "y": float(xy[1])})
        return pid

    def entity(self, kind: str, **values: Any) -> str:
        self.counter += 1
        eid = f"e{self.counter}"
        self.entities.append({"type": kind, "id": eid, **values})
        return eid

    def line(self, start: str, end: str) -> str:
        return self.entity("line", start=start, end=end)

    def arc(self, start: str, end: str, centre: FloatArray, radius: float, ccw: bool) -> str:
        return self.entity(
            "arc",
            start=start,
            end=end,
            center=[float(centre[0]), float(centre[1])],
            radius=float(radius),
            ccw=ccw,
        )

    def constrain(self, kind: str, *refs: str) -> None:
        self.constraints.append({"kind": kind, "refs": list(refs)})


def chain_loop(sketch: SketchDraft, chain: Chain, shift: FloatArray) -> str:
    """Add an outline's lines and arcs to the sketch (moved by `shift`); returns its loop id."""
    return chain_entities(sketch, chain, shift)[0]


def chain_entities(sketch: SketchDraft, chain: Chain, shift: FloatArray) -> list[str]:
    """Add an outline's lines and arcs to the sketch; returns their ids in chain order.

    Neighbouring edges share their point; the chain's relations become constraints.
    The first id is the loop's.
    """
    if chain.is_circle:
        edge = chain.edges[0]
        assert edge.centre is not None
        centre = np.array(edge.centre) + shift
        return [sketch.entity("circle", center=as_list(centre), radius=edge.radius)]
    ids = [sketch.point(np.array(edge.start) + shift) for edge in chain.edges]
    entities: list[str] = []
    for i, edge in enumerate(chain.edges):
        start, end = ids[i], ids[(i + 1) % len(ids)]
        if edge.centre is None:
            entities.append(sketch.line(start, end))
        else:
            centre = np.array(edge.centre) + shift
            entities.append(sketch.arc(start, end, centre, edge.radius, edge.ccw))
    for kind, refs in chain.relations:
        sketch.constrain(kind, *(entities[ref] for ref in refs))
    return entities


def as_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in values]
