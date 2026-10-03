"""Design intent: the regularities a designer put into the features, restored.

Scanned features carry noise: ten equal buttons measure ten slightly different sizes,
the arms of a direction pad do not share a centre exactly. Beautification (after
Langbein, Marshall and Martin 2004: detect candidate regularities within the
measurement uncertainty, then enforce them consistently) restores them:

1. Concentric groups: ring segments and circles whose centres agree share one centre.
   The ring segments of a group are refit together on their measured contours as
   equal arms around one centre (one inner and outer radius, gap, corner and
   sweep) and, when they are spread evenly, with their middles on an exact angular
   pitch; sweep and gap trade off against each other, so they cannot be averaged
   one by one. The arms' centre is the group's centre (four large contours fix it
   better than a small button); if equal arms do not fit, the arms keep their own
   values and the circles share their mean centre.
2. Equal groups: features of the same shape whose dimensions agree get the mean
   dimensions.
3. Rows and columns: centres that agree in u (or v) share the mean value.
4. Directions: slots and rectangles nearly parallel to a plane axis become parallel.
5. Heights that agree become equal: first within a family of equal features (the
   same button made several times has one height), then across families on the same
   level when their heights agree closely.
6. Lengths and heights are rounded to `ROUND_MM` where that stays within the
   uncertainty; a feature standing in a pocket stands on the pocket's rounded floor.

Every step changes values by less than its tolerance, so the result still fits the
scan.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

import numpy as np
from scipy.optimize import least_squares

from m2c_kernel.recognition.outline import DISTANCES, PARAMETERS, Outline
from m2c_kernel.recognition.relief import Relief

CENTRE_MM = 0.6
"""Centres closer than this are taken as the same centre or the same row."""
CENTRE_SHARE = 0.08
"""Round features of radius r share a centre within CENTRE_SHARE x r (if larger)."""
SIZE_MM = 0.2
SIZE_SHARE = 0.03
"""Dimensions within max(SIZE_MM, SIZE_SHARE x size) are taken as equal."""
ANGLE_DEG = 3.0
SHARED_ARM = ("inner", "outer", "gap", "corner", "sweep")
"""What the arms of a ring share; their middles differ by the pitch."""
ARM_SLACK = 2.0
ARM_FLOOR_MM = 0.15
"""Equal arms are kept when each fits its contour within ARM_SLACK x its own fit's RMS
or ARM_FLOOR_MM: scans of moulded parts warp by about a tenth of a millimetre, which
is no reason to model the arms of a direction pad differently."""
HEIGHT_MM = 0.12
"""Equal features whose heights spread less than this share one height."""
SHARED_HEIGHT_MM = 0.05
"""Families whose heights differ less than this share one height."""
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
    _concentric(kinds, outlines, [relief.contour for relief in reliefs])
    _equal_sizes(kinds, outlines)
    # A ring segment's centre lies far outside it: it forms no row with other features.
    in_rows = [i for i, kind in enumerate(kinds) if kind not in ("profile", "ringSegment")]
    for axis in ("cx", "cy"):
        _align(outlines, axis, in_rows)
    _directions(kinds, outlines)
    heights = _equal_heights(reliefs, kinds, outlines)
    # Parents come before their children (relief.py).
    levels = [relief.level for relief in reliefs]
    for i, relief in enumerate(reliefs):
        if relief.parent is not None:
            levels[i] = levels[relief.parent] - heights[relief.parent]
    for values, kind in zip(outlines, kinds, strict=True):
        for name in _LENGTHS[kind]:
            values[name] = _rounded(values[name])
    return [
        replace(
            relief,
            outline=Outline(
                kind, tuple(values[name] for name in PARAMETERS[kind]), relief.outline.rms
            ),
            level=level,
            height=height,
        )
        for relief, values, kind, level, height in zip(
            reliefs, outlines, kinds, levels, heights, strict=True
        )
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


def _concentric(
    kinds: Sequence[str], outlines: list[dict[str, float]], contours: Sequence[np.ndarray]
) -> None:
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
        arms = [i for i in members if kinds[i] == "ringSegment"]
        anchor = _equal_arms(outlines, arms, contours) if len(arms) >= 2 else None
        if anchor is None:
            anchor = np.mean([centre(i) for i in (circles or members)], axis=0)
            # Arms that did not fit as equal arms keep their own centres.
            members = circles or members
        for i in members:
            outlines[i]["cx"], outlines[i]["cy"] = float(anchor[0]), float(anchor[1])


def _even_pitch(middles: np.ndarray) -> tuple[float, np.ndarray] | None:
    """Phase and pitch slots of arm middles spread evenly around a centre, if they are."""
    count = len(middles)
    pitch = TAU / count
    # The common phase of the arms on the pitch grid (circular mean of n x angle).
    phase = float(np.angle(np.mean(np.exp(1j * count * middles)))) / count
    slots = np.round((middles - phase) / pitch)
    misfit = np.abs(middles - phase - slots * pitch)
    if len(set(np.mod(slots, count).astype(int))) != count:
        return None
    if np.degrees(misfit.max()) > 4.0 * ANGLE_DEG:
        return None
    return phase, slots


def _equal_arms(
    outlines: list[dict[str, float]], arms: list[int], contours: Sequence[np.ndarray]
) -> np.ndarray | None:
    """Refit the arms of a ring as equal arms around one centre; that centre, if they fit."""
    distance = DISTANCES["ringSegment"]
    before = [
        _rms(distance(np.array([outlines[i][n] for n in PARAMETERS["ringSegment"]]), contours[i]))
        for i in arms
    ]
    middles = np.array([outlines[i]["start"] + outlines[i]["sweep"] / 2.0 for i in arms])
    even = _even_pitch(middles)
    shared = [float(np.mean([outlines[i][n] for i in arms])) for n in ("cx", "cy", *SHARED_ARM)]
    if even is None:
        start: list[float] = [*shared, *middles]
    else:
        start = [*shared, even[0]]

    def arm_params(x: np.ndarray, k: int) -> np.ndarray:
        cx, cy, inner, outer, gap, corner, sweep = x[:7]
        middle = x[7 + k] if even is None else x[7] + even[1][k] * TAU / len(arms)
        return np.array([cx, cy, inner, outer, middle - sweep / 2.0, sweep, gap, corner])

    def residuals(x: np.ndarray) -> np.ndarray:
        return np.concatenate([distance(arm_params(x, k), contours[i]) for k, i in enumerate(arms)])

    solution = least_squares(residuals, start, loss="soft_l1", f_scale=0.02, max_nfev=400)
    after = [_rms(distance(arm_params(solution.x, k), contours[i])) for k, i in enumerate(arms)]
    if any(a > max(ARM_SLACK * b, ARM_FLOOR_MM) for a, b in zip(after, before, strict=True)):
        return None  # not equal arms: keep each arm's own fit
    for k, i in enumerate(arms):
        values = arm_params(solution.x, k)
        for name, value in zip(PARAMETERS["ringSegment"], values, strict=True):
            outlines[i][name] = float(value)
        outlines[i]["start"] = float(np.mod(outlines[i]["start"], TAU))
    result: np.ndarray = solution.x[:2]
    return result


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(values**2)))


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


def _equal_heights(
    reliefs: Sequence[Relief], kinds: Sequence[str], outlines: Sequence[dict[str, float]]
) -> list[float]:
    heights = [relief.height for relief in reliefs]
    levels: dict[tuple[str, float], list[int]] = {}
    for i, relief in enumerate(reliefs):
        levels.setdefault((relief.kind, round(relief.level, 3)), []).append(i)
    for members in levels.values():
        # Families: equal shape and size (equal sizes are identical by now).
        families: dict[tuple[object, ...], list[int]] = {}
        for i in members:
            size = tuple(round(outlines[i][name], 3) for name in _LENGTHS[kinds[i]])
            key = (kinds[i], size) if kinds[i] != "profile" else ("profile", i)
            families.setdefault(key, []).append(i)
        groups: list[list[int]] = []
        for family in families.values():
            values = [heights[i] for i in family]
            if max(values) - min(values) < HEIGHT_MM:
                groups.append(family)
            else:
                groups.extend([i] for i in family)
        means = [float(np.mean([heights[i] for i in group])) for group in groups]
        for group in groups:
            mean = float(np.mean([heights[i] for i in group]))
            for i in group:
                heights[i] = mean
        for run in _runs(means, SHARED_HEIGHT_MM):
            indices = [i for k in run for i in groups[k]]
            mean = float(np.mean([heights[i] for i in indices]))
            for i in indices:
                heights[i] = mean
    return [_rounded(height) for height in heights]


def _rounded(value: float) -> float:
    return float(np.round(value / ROUND_MM) * ROUND_MM)
