"""Patch layout of a quad net: few large rectangles of quads instead of one face per quad.

Exporting every net quad as its own B-spline face gives CAD bodies with thousands of
faces. Most of a net is a regular grid, though, and a rectangular block of a regular
grid is one bicubic B-spline surface. The layout cuts the net into such blocks:

1. Motorcycle graph (Eppstein et al. 2008): from every irregular point a trace runs
   straight along each of its edges, all traces advancing one edge per round. A
   trace stops on the net's border, at an irregular point, on another trace or on
   an edge another trace has already taken. Irregular points then sit only at block
   corners, so every block is a grid of quads with regular points inside.
2. Blocks are the quads connected across uncut edges. A block that is not a simple
   rectangle (a ring around a cylinder, a torus without irregular points, a block
   whose sides touch) is cut again by traces from a point in its middle, and given up
   as single quads if that does not help.
3. Lines are the cut edges joined straight through regular points. Every block side
   lies on one line, so neighbouring faces can share one boundary curve per line
   even where a side of one block covers several blocks on the other side
   (T-junctions).

Grid frame of a block: cell (i, j) covers [i, i + 1] x [j, j + 1]; `rotations[i, j]`
is the quad corner at the cell's (0, 0) corner, and the quad's corners follow
counter-clockwise, so the frame keeps the net's orientation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from m2c_kernel.surfacing.subdivision import EdgeTopology

type IntArray = npt.NDArray[np.int64]
type BoolArray = npt.NDArray[np.bool_]

MAX_SPLITS = 64
"""Extra traces tried per layout before stubborn blocks are given up as single quads."""

# Grid step of each cell side seen from the cell: bottom, right, top, left.
_STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass(frozen=True)
class Block:
    """A rectangle of a x b net quads.

    Attributes:
        cells: (a, b) quad of every cell.
        rotations: (a, b) quad corner at the (0, 0) corner of every cell.
        nodes: (a + 1, b + 1) net vertex at every grid point.
    """

    cells: IntArray
    rotations: IntArray
    nodes: IntArray

    @property
    def size(self) -> tuple[int, int]:
        return int(self.cells.shape[0]), int(self.cells.shape[1])


@dataclass(frozen=True)
class Line:
    """Cut edges joined straight through regular points.

    Attributes:
        vertices: (n + 1,) net vertices along the line; a closed line repeats its first
            vertex at the end.
        edges: (n,) net edge from `vertices[k]` to `vertices[k + 1]`.
        closed: Whether the line is a loop.
    """

    vertices: IntArray
    edges: IntArray
    closed: bool

    @property
    def length(self) -> int:
        return len(self.edges)


@dataclass(frozen=True)
class PatchLayout:
    """Blocks, lines and corners of a net.

    Attributes:
        blocks: The rectangles; together they cover every quad once.
        lines: The lines along all block sides.
        edge_line: (e,) line of every net edge, -1 inside a block.
        edge_position: (e,) index of the edge within its line.
        corners: (n,) True for net vertices at a block corner; the B-Rep vertices.
    """

    blocks: tuple[Block, ...]
    lines: tuple[Line, ...]
    edge_line: IntArray
    edge_position: IntArray
    corners: BoolArray


class _Net:
    """Adjacency of a quad net, as the layout steps need it."""

    def __init__(self, quads: IntArray, topology: EdgeTopology) -> None:
        self.quads = quads
        self.topology = topology
        n = topology.n_vertices
        edges = topology.edges
        self.valence = np.bincount(edges.ravel(), minlength=n)
        border_edges = topology.boundary
        self.border_vertex = np.zeros(n, dtype=bool)
        self.border_vertex[edges[border_edges].ravel()] = True
        # Vertex -> incident edges (CSR).
        ends = edges.ravel()
        order = np.argsort(ends, kind="stable")
        self.vertex_edge_start = np.concatenate([[0], np.cumsum(np.bincount(ends, minlength=n))])
        self.vertex_edges = (order // 2).astype(np.int64)
        regular_interior = ~self.border_vertex & (self.valence == 4)
        regular_border = self.border_vertex & (self.valence == 3)
        self.regular = regular_interior | regular_border

    def edges_at(self, vertex: int) -> IntArray:
        return self.vertex_edges[
            self.vertex_edge_start[vertex] : self.vertex_edge_start[vertex + 1]
        ]

    def other_end(self, edge: int, vertex: int) -> int:
        a, b = self.topology.edges[edge]
        return int(b if a == vertex else a)

    def straight(self, vertex: int, edge: int) -> int:
        """The edge leaving a regular point opposite to `edge`, or -1."""
        if not self.regular[vertex]:
            return -1
        topology = self.topology
        if self.border_vertex[vertex]:
            if not topology.boundary[edge]:
                return -1
            others = [int(e) for e in self.edges_at(vertex) if e != edge and topology.boundary[e]]
            return others[0] if others else -1
        beside: set[int] = {edge}
        for face in topology.edge_faces[edge]:
            corner = int(np.flatnonzero(self.quads[face] == vertex)[0])
            beside.add(int(topology.face_edges[face, corner]))
            beside.add(int(topology.face_edges[face, corner - 1]))
        rest = [int(e) for e in self.edges_at(vertex) if int(e) not in beside]
        return rest[0] if len(rest) == 1 else -1


def patch_layout(
    quads: IntArray,
    topology: EdgeTopology,
    check_cancelled: Callable[[], None] = lambda: None,
) -> PatchLayout:
    """Cut a net into rectangles of quads (module docstring)."""
    net = _Net(quads, topology)
    cut = topology.boundary.copy()
    visited = net.border_vertex | ~net.regular
    seeds = np.flatnonzero(~net.regular)
    _trace(net, [(v, int(e)) for v in seeds.tolist() for e in net.edges_at(v)], cut, visited)
    check_cancelled()

    blocks, stubborn = _blocks(net, cut, visited, check_cancelled)
    while True:
        separate = _separating(net, blocks, stubborn)
        lines, edge_line, edge_position = _lines(net, separate)
        bad = {
            k
            for k, block in enumerate(blocks)
            if not _on_lines(block, lines, edge_line, edge_position, topology)
        }
        if not bad:
            break
        for k in bad:
            stubborn.extend(int(q) for q in blocks[k].cells.ravel())
        blocks = [block for k, block in enumerate(blocks) if k not in bad]
    blocks.extend(_single(quads, int(q)) for q in sorted(stubborn))
    corners = np.zeros(topology.n_vertices, dtype=bool)
    for block in blocks:
        corners[block.nodes[[0, 0, -1, -1], [0, -1, 0, -1]]] = True
    return PatchLayout(
        blocks=tuple(blocks),
        lines=tuple(lines),
        edge_line=edge_line,
        edge_position=edge_position,
        corners=corners,
    )


def _trace(net: _Net, starts: list[tuple[int, int]], cut: BoolArray, visited: BoolArray) -> None:
    """Advance all traces one edge per round until each one stops."""
    riders = [(vertex, edge) for vertex, edge in starts if not cut[edge]]
    while riders:
        moving: list[tuple[int, int]] = []
        for vertex, edge in riders:
            if cut[edge]:
                continue
            cut[edge] = True
            ahead = net.other_end(edge, vertex)
            if visited[ahead]:
                continue
            visited[ahead] = True
            following = net.straight(ahead, edge)
            if following >= 0:
                moving.append((ahead, following))
        riders = moving


def _blocks(
    net: _Net, cut: BoolArray, visited: BoolArray, check_cancelled: Callable[[], None]
) -> tuple[list[Block], list[int]]:
    """Rectangles of the quads between cut edges; quads that form none are returned apart."""
    blocks: list[Block] = []
    stubborn: list[int] = []
    pending = deque(_regions(net, cut, np.arange(len(net.quads))))
    splits = 0
    while pending:
        check_cancelled()
        region = pending.popleft()
        block = _rectangle(net, region, cut)
        if block is not None:
            blocks.append(block)
            continue
        seed = _middle_vertex(net, region, cut, visited) if splits < MAX_SPLITS else -1
        if seed < 0:
            stubborn.extend(int(q) for q in region)
            continue
        splits += 1
        visited[seed] = True
        _trace(net, [(seed, int(e)) for e in net.edges_at(seed)], cut, visited)
        pending.extend(_regions(net, cut, region))
    return blocks, stubborn


def _regions(net: _Net, cut: BoolArray, quads: IntArray) -> list[IntArray]:
    """The given quads grouped by connection across uncut edges."""
    topology = net.topology
    member = np.full(len(net.quads), -1, dtype=np.int64)
    member[quads] = 0
    regions: list[IntArray] = []
    for start in quads:
        if member[start] != 0:
            continue
        label = len(regions) + 1
        member[start] = label
        found = [int(start)]
        queue = deque(found)
        while queue:
            quad = queue.popleft()
            for edge in topology.face_edges[quad]:
                if cut[edge]:
                    continue
                for other in topology.edge_faces[edge]:
                    if other >= 0 and member[other] == 0:
                        member[other] = label
                        found.append(int(other))
                        queue.append(int(other))
        regions.append(np.asarray(found, dtype=np.int64))
    return regions


def _rectangle(net: _Net, region: IntArray, cut: BoolArray) -> Block | None:
    """The region as a grid of quads, or None when it is not a simple rectangle."""
    topology = net.topology
    start = int(region[0])
    place: dict[int, tuple[int, int, int]] = {start: (0, 0, 0)}
    queue = deque([start])
    while queue:
        quad = queue.popleft()
        i, j, rotation = place[quad]
        for direction, (di, dj) in enumerate(_STEPS):
            edge = int(topology.face_edges[quad, (rotation + direction) % 4])
            if cut[edge]:
                continue
            faces = topology.edge_faces[edge]
            other = int(faces[1] if faces[0] == quad else faces[0])
            side = int(np.flatnonzero(topology.face_edges[other] == edge)[0])
            wanted = (i + di, j + dj, (side - direction - 2) % 4)
            if other in place:
                if place[other] != wanted:
                    return None
                continue
            place[other] = wanted
            queue.append(other)

    keys = np.array(list(place.values()), dtype=np.int64)
    low = keys[:, :2].min(axis=0)
    a, b = (keys[:, :2].max(axis=0) - low + 1).tolist()
    if a * b != len(place):
        return None
    cells = np.full((a, b), -1, dtype=np.int64)
    rotations = np.zeros((a, b), dtype=np.int64)
    for quad, (i, j, rotation) in place.items():
        if cells[i - low[0], j - low[1]] >= 0:
            return None
        cells[i - low[0], j - low[1]] = quad
        rotations[i - low[0], j - low[1]] = rotation
    nodes = np.full((a + 1, b + 1), -1, dtype=np.int64)
    for corner, (ci, cj) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        vertices = net.quads[cells, (rotations + corner) % 4]
        target = nodes[ci : ci + a, cj : cj + b]
        if np.any((target >= 0) & (target != vertices)):
            return None
        target[...] = vertices
    if len(np.unique(nodes)) != nodes.size:
        return None
    return Block(cells=cells, rotations=rotations, nodes=nodes)


def _middle_vertex(net: _Net, region: IntArray, cut: BoolArray, visited: BoolArray) -> int:
    """A free regular point deep inside the region (far from cut edges), or -1."""
    topology = net.topology
    depth = {int(q): 0 for q in region if np.any(cut[topology.face_edges[q]])}
    if not depth:
        depth = {int(region[0]): 0}
    queue = deque(depth)
    members = set(int(q) for q in region)
    while queue:
        quad = queue.popleft()
        for edge in topology.face_edges[quad]:
            for other in topology.edge_faces[edge]:
                other = int(other)
                if other in members and other not in depth:
                    depth[other] = depth[quad] + 1
                    queue.append(other)
    for quad in sorted(depth, key=lambda q: -depth[q]):
        for vertex in net.quads[quad]:
            if not visited[vertex] and net.regular[vertex] and not net.border_vertex[vertex]:
                return int(vertex)
    return -1


def _single(quads: IntArray, quad: int) -> Block:
    return Block(
        cells=np.array([[quad]], dtype=np.int64),
        rotations=np.zeros((1, 1), dtype=np.int64),
        nodes=np.array([[quads[quad, 0], quads[quad, 3]], [quads[quad, 1], quads[quad, 2]]]),
    )


def _separating(net: _Net, blocks: list[Block], stubborn: list[int]) -> BoolArray:
    """Net edges between different blocks (single quads count as blocks) or on the border."""
    topology = net.topology
    owner = np.full(len(net.quads), -1, dtype=np.int64)
    for label, block in enumerate(blocks):
        owner[block.cells.ravel()] = label
    for offset, quad in enumerate(stubborn):
        owner[quad] = len(blocks) + offset
    faces = topology.edge_faces
    other = np.where(faces[:, 1] >= 0, owner[np.maximum(faces[:, 1], 0)], -2)
    separate: BoolArray = topology.boundary | (owner[faces[:, 0]] != other)
    return separate


def _lines(net: _Net, separate: BoolArray) -> tuple[list[Line], IntArray, IntArray]:
    """Separating edges joined straight through regular points into lines."""
    n_edges = len(separate)
    edge_line = np.full(n_edges, -1, dtype=np.int64)
    edge_position = np.full(n_edges, -1, dtype=np.int64)
    lines: list[Line] = []

    def onward(vertex: int, edge: int) -> int:
        following = net.straight(vertex, edge)
        return following if following >= 0 and separate[following] else -1

    for first in np.flatnonzero(separate):
        if edge_line[first] >= 0:
            continue
        # Walk backwards to the line's start (or once round a closed line), then forwards.
        tail, edge, closed = int(net.topology.edges[first][0]), int(first), False
        while True:
            previous = onward(tail, edge)
            if previous < 0:
                break
            if previous == first:
                closed = True
                break
            tail, edge = net.other_end(previous, tail), previous
        if closed:
            tail, edge = int(net.topology.edges[first][0]), int(first)
        start = tail
        vertices, edges = [start], []
        vertex = start
        while True:
            edges.append(edge)
            vertex = net.other_end(edge, vertex)
            vertices.append(vertex)
            edge = onward(vertex, edge)
            if edge < 0 or edge == edges[0]:
                break
        label = len(lines)
        edge_line[edges] = label
        edge_position[edges] = np.arange(len(edges))
        lines.append(
            Line(
                vertices=np.asarray(vertices, dtype=np.int64),
                edges=np.asarray(edges, dtype=np.int64),
                closed=closed,
            )
        )
    return lines, edge_line, edge_position


def block_sides(block: Block) -> tuple[IntArray, IntArray, IntArray, IntArray]:
    """Grid nodes along the sides in the grid's own directions: bottom, right, top, left.

    Bottom and top run with i, left and right with j.
    """
    nodes = block.nodes
    return nodes[:, 0], nodes[-1, :], nodes[:, -1], nodes[0, :]


def side_on_line(
    side: IntArray,
    lines: tuple[Line, ...] | list[Line],
    edge_line: IntArray,
    edge_position: IntArray,
    topology: EdgeTopology,
) -> tuple[int, int, int] | None:
    """Where a block side lies on its line: (line, position of its first node, step).

    `step` is +1 when the side runs along the line's direction, -1 against it. None
    when the side does not lie on a single line.
    """
    edges = topology.edge_ids(side[:-1], side[1:])
    line = int(edge_line[edges[0]])
    if line < 0 or np.any(edge_line[edges] != line):
        return None
    current = lines[line]
    k = int(edge_position[edges[0]])
    step = 1 if current.vertices[k] == side[0] else -1
    start = k if step == 1 else k + 1
    positions = start + step * np.arange(len(side))
    if current.closed:
        positions %= current.length
    elif positions.min() < 0 or positions.max() > current.length:
        return None
    if np.any(current.vertices[positions] != side):
        return None
    return line, start, step


def _on_lines(
    block: Block,
    lines: list[Line],
    edge_line: IntArray,
    edge_position: IntArray,
    topology: EdgeTopology,
) -> bool:
    return all(
        side_on_line(side, lines, edge_line, edge_position, topology) is not None
        for side in block_sides(block)
    )
