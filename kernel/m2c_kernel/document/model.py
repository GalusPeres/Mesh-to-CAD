"""The document: scan, alignment, regions, feature history and project settings.

All classes are immutable. A command that changes the document builds a new
`Document` and commits it through the session; nothing mutates a document in
place. The JSON form produced by `m2c_kernel.protocol.wire.to_json` is what is
persisted in revisions and project files and what the renderer mirrors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from m2c_kernel.geometry import IDENTITY, Matrix4, Vec3
from m2c_kernel.limits import DEFAULT_TOLERANCE_MM
from m2c_kernel.protocol.wire import BlobRef, JsonValue
from m2c_kernel.snapping import SnapUnits

DOCUMENT_FORMAT = "mesh-to-cad-document"
DOCUMENT_VERSION = 1

type LengthUnit = Literal["mm", "cm", "m", "in"]
type RegionKind = Literal["plane", "cylinder", "cone", "sphere", "torus", "freeform", "unknown"]


@dataclass(frozen=True)
class ScanSource:
    file_name: str
    sha256: str
    import_unit: LengthUnit


@dataclass(frozen=True)
class ScanOperation:
    """One entry of the scan's preparation log (import, repair, reduce, ...)."""

    op: str
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Scan:
    """The working mesh, stored in scan coordinates.

    `key` identifies the exact vertex and face arrays. The renderer tags selection
    state with it, so selections made on an older mesh are recognised as stale.
    `synthetic` marks faces created by hole filling (1 = synthetic); fitting,
    segmentation and deviation statistics exclude them.
    """

    key: str
    source: ScanSource
    vertices: BlobRef
    faces: BlobRef
    synthetic: BlobRef | None
    vertex_count: int
    face_count: int
    origin: Vec3
    noise: float | None
    display_smoothing: int = 0
    operations: tuple[ScanOperation, ...] = ()


@dataclass(frozen=True)
class AlignmentAdjust:
    flip_x: bool = False
    flip_z: bool = False
    rotate_z90: int = 0


@dataclass(frozen=True)
class Alignment:
    """How scan coordinates map to part coordinates.

    `params` holds the method-specific inputs; `m2c_kernel.alignment` defines and
    validates them. `matrix` is the last evaluated result.
    """

    method: Literal["none", "auto", "faces"] = "none"
    params: JsonValue = None
    adjust: AlignmentAdjust = AlignmentAdjust()
    matrix: Matrix4 = IDENTITY


@dataclass(frozen=True)
class Region:
    id: str
    label: int
    name: str | None
    kind: RegionKind
    rms: float | None
    face_count: int
    area: float
    color_index: int


@dataclass(frozen=True)
class Regions:
    """Disjoint face groups: one uint16 label per face in `labels`, 0 = unassigned."""

    labels: BlobRef | None = None
    items: tuple[Region, ...] = ()


@dataclass(frozen=True)
class Feature:
    """One entry of the history. `params` follow the feature type's `Params` dataclass."""

    id: str
    type: str
    name: str | None
    suppressed: bool
    params: JsonValue


@dataclass(frozen=True)
class DocumentSettings:
    """Project settings that influence results.

    `tolerance` is the single project tolerance for pass/fail colouring, fit
    verdicts and the deviation map. `snap_units` selects the value steps of
    design-intent snapping in fits and sketches.
    """

    tolerance: float = DEFAULT_TOLERANCE_MM
    snap_units: SnapUnits = "metric"
    noise_override: float | None = None
    deviation_max_distance: float = 2.0


@dataclass(frozen=True)
class Document:
    revision: int
    next_id: int
    scan: Scan | None
    alignment: Alignment
    regions: Regions
    features: tuple[Feature, ...]
    settings: DocumentSettings

    @classmethod
    def empty(cls) -> Document:
        return cls(
            revision=0,
            next_id=1,
            scan=None,
            alignment=Alignment(),
            regions=Regions(),
            features=(),
            settings=DocumentSettings(),
        )

    def feature(self, feature_id: str) -> Feature | None:
        return next((item for item in self.features if item.id == feature_id), None)

    def blob_refs(self) -> set[BlobRef]:
        """Every blob this document references (for garbage collection and project files)."""
        refs: set[BlobRef] = set()
        if self.scan is not None:
            refs.update((self.scan.vertices, self.scan.faces))
            if self.scan.synthetic is not None:
                refs.add(self.scan.synthetic)
        if self.regions.labels is not None:
            refs.add(self.regions.labels)
        for feature in self.features:
            refs.update(_blob_refs_in(feature.params))
        refs.update(_blob_refs_in(self.alignment.params))
        return refs


def _blob_refs_in(value: JsonValue) -> set[BlobRef]:
    if isinstance(value, str):
        return {value} if value.startswith("blob:") else set()
    if isinstance(value, list):
        return set().union(*(_blob_refs_in(item) for item in value)) if value else set()
    if isinstance(value, dict):
        return set().union(*(_blob_refs_in(item) for item in value.values())) if value else set()
    return set()
