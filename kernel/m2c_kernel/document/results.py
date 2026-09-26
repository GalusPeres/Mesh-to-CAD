"""What features produce, and the status the rebuild reports for them.

Two kinds of types live here:

- Wire types (`Issue`, `FeatureStatus`, `BodyInfo`, ...) are sent to the
  renderer in `documentChanged` and in preview results.
- Runtime types (`FeatureOutput`, `Body`, `SketchResult`, `Construction`,
  `DisplaySource`) stay in the kernel. They may hold Open CASCADE shapes and
  numpy arrays and never cross the protocol.

**Face tags.** Every body carries one tag per B-Rep face, aligned with the face
order of `TopExp.MapShapes_s(shape, TopAbs_FACE)`. A feature tags the faces it
creates (an extrusion: `cap:start`, `cap:end`, `side:<entityId>`; a primitive
body: its role, for example `lateral`) prefixed with its feature id, and carries
existing tags through booleans and fillets with the operation history
(`Modified()` / `Generated()`). Edge references of fillets are pairs of face
tags, so they survive upstream parameter changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.fitting.primitives import Axis, Primitive
from m2c_kernel.protocol.wire import JsonValue

type FeatureState = Literal["ok", "warning", "error", "suppressed", "skipped"]
type DisplayKind = Literal["mesh", "lines", "points"]
type DisplayStyle = Literal[
    "body",
    "bodyEdges",
    "previewBody",
    "construction",
    "constructionEdges",
    "patch",
    "sketch",
    "sketchPoints",
    "section",
    "sectionPoints",
]


@dataclass(frozen=True)
class Issue:
    """A warning with a translatable code (i18n namespace `issues`)."""

    code: str
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorInfo:
    """A failure with a translatable code (i18n namespace `errors`)."""

    code: str
    params: dict[str, JsonValue] = field(default_factory=dict)
    details: str | None = None


@dataclass(frozen=True)
class FeatureStatus:
    state: FeatureState
    issues: tuple[Issue, ...] = ()
    error: ErrorInfo | None = None
    stats: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class BodyInfo:
    id: str
    owner: str
    valid: bool
    solids: int
    volume: float
    area: float
    max_tolerance: float
    face_tags: tuple[str, ...] = ()
    """Tag per B-Rep face; `faceIds` and edge `faces` of the display payloads index into it."""


@dataclass(frozen=True)
class Body:
    """A solid body: the shape plus one tag per B-Rep face (see module docstring)."""

    shape: Any
    face_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class BodyUpdate:
    """Bodies a feature creates or modifies (by body id) and bodies it removes."""

    changed: Mapping[str, Body] = field(default_factory=dict)
    removed: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaneFrame:
    """A plane with an explicit in-plane X direction (sketch coordinates depend on it)."""

    origin: npt.NDArray[np.float64]
    x_dir: npt.NDArray[np.float64]
    normal: npt.NDArray[np.float64]

    @property
    def y_dir(self) -> npt.NDArray[np.float64]:
        return np.cross(self.normal, self.x_dir)


@dataclass(frozen=True)
class SketchResult:
    """A finished sketch: its plane and the planar faces of its closed profiles.

    `profile_faces` are `TopoDS_Face` objects (outer loops counter-clockwise,
    holes clockwise). `loop_ids` names the loop each face was built from, so
    extrusions can select loops.
    """

    frame: PlaneFrame
    profile_faces: tuple[Any, ...] = ()
    loop_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Construction:
    """Reference geometry: a fitted or constructed primitive, an axis, a point or a patch."""

    primitive: Primitive | None = None
    axis: Axis | None = None
    point: npt.NDArray[np.float64] | None = None
    surface: Any = None


@dataclass(frozen=True)
class DisplaySource:
    """Geometry a feature wants drawn besides its bodies (bodies are tessellated centrally).

    Positions are in part coordinates. Meshes need `indices` (m, 3); lines use
    `positions` as (s, 2, 3) segments with optional per-segment `ids`.
    """

    kind: DisplayKind
    style: DisplayStyle
    positions: npt.NDArray[np.float64]
    indices: npt.NDArray[np.int64] | None = None
    ids: npt.NDArray[np.uint32] | None = None


@dataclass(frozen=True)
class FeatureOutput:
    construction: Construction | None = None
    sketch: SketchResult | None = None
    bodies: BodyUpdate = BodyUpdate()
    display: tuple[DisplaySource, ...] = ()
    stats: Mapping[str, float | None] = field(default_factory=dict)
    issues: tuple[Issue, ...] = ()
