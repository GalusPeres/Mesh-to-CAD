"""Design intent: the regularities a designer put into the features, restored.

Scanned features carry noise: ten equal buttons measure ten slightly different sizes,
the arms of a direction pad do not share a centre exactly. Beautification (after
Langbein, Marshall and Martin 2004: detect candidate regularities within the
measurement uncertainty, then enforce them consistently) restores them:

1. Concentric groups: ring segments and circles whose centres agree share one centre
   (a circle's centre wins); the ring segments of a group get equal radii, gap and
   corner, and when they are spread evenly, an exact angular pitch.
2. Equal groups: features of the same shape whose dimensions agree get the mean
   dimensions.
3. Rows and columns: centres that agree in u (or v) share the mean value.
4. Directions: slots and rectangles nearly parallel to a plane axis become parallel.
5. Heights that agree become equal.
6. Lengths and heights are rounded to `ROUND_MM` where that stays within the
   uncertainty.

Every step changes values by less than its tolerance, so the result still fits the
scan.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

import numpy as np

from m2c_kernel.recognition.outline import PARAMETERS, Outline
from m2c_kernel.recognition.relief import Relief

CENTRE_MM = 0.6
"""Centres closer than this are taken as the same centre or the same row."""
CENTRE_SHARE = 0.08
"""Round features of radius r share a centre within CENTRE_SHARE x r (if larger)."""
SIZE_MM = 0.2
SIZE_SHARE = 0.03
"""Dimensions within max(SIZE_MM, SIZE_SHARE x size) are taken as equal."""
ANGLE_DEG = 3.0
HEIGHT_MM = 0.12
ROUND_MM = 0.05
TAU = 2.0 * np.pi

_LENGTHS: dict[str, tuple[str, ...]] = {
    "circle": ("radius",),
    "slot": ("length", "width"),
    "roundedRect": ("width", "height", "corner"),
    "ringSegment": ("inner", "outer", "gap", "corner"),
    "profile": (),
}


def beautify(reliefs: Sequence[Relief]) -> list[Relief]:
    """The reliefs with their regularities enforced (see module docstring)."""
    outlines = [dict(relief.outline.named()) for relief in reliefs]
    kinds = [relief.outline.kind for relief in reliefs]
    _concentric(kinds, outlines)
    _equal_sizes(kinds, outlines)
    for axis in ("cx", "cy"):
        _align(outlines, axis, [i for i, kind in enumerate(kinds) if kind != "profile"])
    _directions(kinds, outlines)
    heights = _equal_heights(reliefs)
    for values, kind in zip(outlines, kinds, strict=True):
        for name in _LENGTHS[kind]:
            values[name] = _rounded(values[name])
    return [
        replace(
            relief,
            outline=Outline(
                kind, tuple(values[name] for name in PARAMETERS[kind]), relief.outline.rms
            ),
            height=height,
        )
        for relief, values, kind, height in zip(reliefs, outlines, kinds, heights, strict=True)
    ]


def _clusters(count: int, close: Callable[[int, int], bool]) -> list[list[int]]:
    """Groups of indices connected by the `close` relation (single linkage)."""
    label = list(range(count))

    def root(i: int) -> int:
        while label[i] != i:
            label[i] = label[label[i]]
            i = label[i]
        return i

    for i in range(count):
        for j in range(i + 1, count):
            if close(i, j):
                label[root(i)] = root(j)
    groups: dict[int, list[int]] = {}
    for i in range(count):
        groups.setdefault(root(i), []).append(i)
    return [group for group in groups.values() if len(group) > 1]


def _concentric(kinds: Sequence[str], outlines: list[dict[str, float]]) -> None:
    round_ones = [i for i, kind in enumerate(kinds) if kind in ("circle", "ringSegment")]
    if len(round_ones) < 2:
        return

    def centre(i: int) -> np.ndarray:
        return np.array([outlines[i]["cx"], outlines[i]["cy"]])

    def reach(i: int) -> float:
        # A ring segment's centre is far from its points, so it is less certain.
        size = outlines[i]["outer"] if kinds[i] == "ringSegment" else outlines[i]["radius"]
        return max(CENTRE_MM, CENTRE_SHARE * size)

    groups = _clusters(
        len(round_ones),
        lambda a, b: bool(
            np.linalg.norm(centre(round_ones[a]) - centre(round_ones[b]))
            < max(reach(round_ones[a]), reach(round_ones[b]))
        ),
    )
    for group in groups:
        members = [round_ones[k] for k in group]
        circles = [i for i in members if kinds[i] == "circle"]
        anchor = np.mean([centre(i) for i in (circles or members)], axis=0)
        for i in members:
            outlines[i]["cx"], outlines[i]["cy"] = float(anchor[0]), float(anchor[1])
        arms = [i for i in members if kinds[i] == "ringSegment"]
        if len(arms) < 2:
            continue
        for name in ("inner", "outer", "gap", "corner"):
            mean = float(np.mean([outlines[i][name] for i in arms]))
            for i in arms:
                outlines[i][name] = mean
        _even_pitch(outlines, arms)


def _even_pitch(outlines: list[dict[str, float]], arms: list[int]) -> None:
    """Arms spread evenly around their centre get an exact pitch of a full turn / n."""
    pitch = TAU / len(arms)
    middles = np.array([outlines[i]["start"] + outlines[i]["sweep"] / 2.0 for i in arms])
    # The common phase of the arms on the pitch grid (circular mean of n x angle).
    phase = float(np.angle(np.mean(np.exp(1j * len(arms) * middles)))) / len(arms)
    slots = np.round((middles - phase) / pitch)
    misfit = np.abs(middles - phase - slots * pitch)
    if len(set(np.mod(slots, len(arms)).astype(int))) != len(arms):
        return
    if np.degrees(misfit.max()) > 4.0 * ANGLE_DEG:
        return
    for i, slot in zip(arms, slots, strict=True):
        middle = phase + slot * pitch
        outlines[i]["sweep"] = pitch
        outlines[i]["start"] = float(np.mod(middle - pitch / 2.0, TAU))


def _equal_sizes(kinds: Sequence[str], outlines: list[dict[str, float]]) -> None:
    for kind in ("circle", "slot", "roundedRect"):
        members = [i for i, k in enumerate(kinds) if k == kind]
        names = _LENGTHS[kind]

        def same(
            a: int, b: int, members: list[int] = members, names: tuple[str, ...] = names
        ) -> bool:
            return all(
                abs(outlines[members[a]][n] - outlines[members[b]][n])
                < max(SIZE_MM, SIZE_SHARE * outlines[members[a]][n])
                for n in names
            )

        for group in _clusters(len(members), same):
            indices = [members[k] for k in group]
            for name in names:
                mean = float(np.mean([outlines[i][name] for i in indices]))
                for i in indices:
                    outlines[i][name] = mean


def _align(outlines: list[dict[str, float]], axis: str, members: list[int]) -> None:
    for group in _runs([outlines[i][axis] for i in members], CENTRE_MM):
        indices = [members[k] for k in group]
        mean = float(np.mean([outlines[i][axis] for i in indices]))
        for i in indices:
            outlines[i][axis] = mean


def _runs(values: Sequence[float], tolerance: float) -> list[list[int]]:
    """Groups of values spanning less than `tolerance` each (no chaining)."""
    order = np.argsort(values)
    groups: list[list[int]] = []
    current: list[int] = []
    for index in order.tolist():
        if current and values[index] - values[current[0]] >= tolerance:
            groups.append(current)
            current = []
        current.append(index)
    if current:
        groups.append(current)
    return [group for group in groups if len(group) > 1]


def _directions(kinds: Sequence[str], outlines: list[dict[str, float]]) -> None:
    for values, kind in zip(outlines, kinds, strict=True):
        if kind not in ("slot", "roundedRect"):
            continue
        quarter = np.pi / 2.0
        snapped = round(values["angle"] / quarter) * quarter
        if abs(np.degrees(values["angle"] - snapped)) < ANGLE_DEG:
            values["angle"] = float(np.mod(snapped, np.pi))


def _equal_heights(reliefs: Sequence[Relief]) -> list[float]:
    heights = [relief.height for relief in reliefs]
    families: dict[tuple[str, float], list[int]] = {}
    for i, relief in enumerate(reliefs):
        families.setdefault((relief.kind, round(relief.level, 3)), []).append(i)
    for members in families.values():
        for group in _runs([heights[i] for i in members], HEIGHT_MM):
            indices = [members[k] for k in group]
            mean = float(np.mean([heights[i] for i in indices]))
            for i in indices:
                heights[i] = mean
    return [_rounded(height) for height in heights]


def _rounded(value: float) -> float:
    return float(np.round(value / ROUND_MM) * ROUND_MM)
