"""Smart selection, regions and automatic segmentation.

`regions.grow` answers the smart-select hover; `regions.segment` splits the scan
into regions (a preview with `dry_run`, then the commit, which reuses the
preview); `regions.create`, `regions.update`, `regions.merge` and
`regions.delete` edit the region list. Region labels are one uint16 per face,
so regions stay disjoint by construction: creating or extending a region moves
its faces out of every other region. See ARCHITECTURE.md 3.5.8 and 4.4.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Annotated, Literal

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.regions import ErrorCode, ProgressStage
from m2c_kernel.document.model import Document, Region, RegionKind, Regions
from m2c_kernel.document.rebuild import EvalMesh
from m2c_kernel.fitting.api import PrimitiveKind
from m2c_kernel.limits import MAX_REGIONS
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import Range, U8Array, U16Array, U32Array
from m2c_kernel.segmentation.api import (
    DEFAULT_MAX_ANGLE_DEG,
    LEVELS_OF_DETAIL,
    GrowMode,
    adjacency,
    assign_colors,
    classify_faces,
    default_tolerance,
    free_labels,
    grow_region,
    is_prepared,
    label_sizes,
    match_regions,
    prepare,
    segment,
)
from m2c_kernel.session.jobs import JobContext, seeded_rng

type LabelArray = npt.NDArray[np.uint16]
type FaceIndices = npt.NDArray[np.int64]

# --------------------------------------------------------------------------- grow


@dataclass(frozen=True)
class GrowParams:
    scan_key: str
    seed_face: int
    mode: GrowMode = "primitive"
    kind: PrimitiveKind | Literal["auto"] = "auto"
    tolerance: Annotated[float, Range(0.001, 10.0)] | None = None
    """Distance limit in mm of the primitive mode; null: 4 x the scan noise."""
    max_angle_deg: Annotated[float, Range(1.0, 60.0)] = DEFAULT_MAX_ANGLE_DEG


@dataclass(frozen=True)
class GrowResult:
    faces: U32Array
    kind: PrimitiveKind | None
    rms: float | None
    tolerance: float
    """The distance limit that was used (mm)."""


@command("regions.grow", lane=True)
def regions_grow(ctx: JobContext, params: GrowParams) -> GrowResult:
    """Grow the surface under a seed face (smart select); does not change the document."""
    mesh = _current_mesh(ctx, params.scan_key)
    if not 0 <= params.seed_face < len(mesh.faces):
        raise KernelError(ErrorCode.INVALID_FACE, {"face": params.seed_face})
    if not is_prepared(mesh):
        ctx.progress(None, ProgressStage.ANALYSING)
        prepare(mesh, ctx.check_cancelled)
    tolerance = params.tolerance or default_tolerance(mesh)
    grown = grow_region(
        mesh,
        params.seed_face,
        params.mode,
        seeded_rng(f"regions.grow:{mesh.key}:{params.seed_face}"),
        kind=None if params.kind == "auto" else params.kind,
        tolerance=tolerance,
        max_angle_deg=params.max_angle_deg,
        check=ctx.check_cancelled,
    )
    return GrowResult(
        faces=grown.faces.astype(np.uint32), kind=grown.kind, rms=grown.rms, tolerance=tolerance
    )


# --------------------------------------------------------------------------- segment


@dataclass(frozen=True)
class SegmentParams:
    scan_key: str
    sensitivity: Annotated[float, Range(0.0, 100.0)] = 50.0
    """0 gives few large regions, 100 many small ones."""
    min_area: Annotated[float, Range(0.0, 10_000.0)] = 2.0
    """Regions below this area (mm^2) are dropped."""
    faces: U32Array | None = None
    """Segment only these faces; regions outside them are kept."""
    dry_run: bool = True


@dataclass(frozen=True)
class SegmentedRegion:
    label: int
    kind: PrimitiveKind
    rms: float
    face_count: int
    area: float
    color_index: int


@dataclass(frozen=True)
class SegmentResult:
    """The regions found. A preview also returns the labels of the resulting document.

    The labels (one per face) and the palette index per label value describe every
    region after the commit, including kept regions outside `faces`; `regions`
    lists only the new ones.
    """

    regions: list[SegmentedRegion]
    labels: U16Array | None
    color_index: U8Array | None
    revision: int | None


@dataclass(frozen=True)
class _Outcome:
    regions: Regions
    labels: LabelArray
    found: list[SegmentedRegion]
    next_id: int


class _PreviewCache:
    """The last segmentation preview, so the commit that follows it is immediate."""

    def __init__(self) -> None:
        self._key: str | None = None
        self._outcome: _Outcome | None = None

    def get(self, key: str) -> _Outcome | None:
        return self._outcome if key == self._key else None

    def put(self, key: str, outcome: _Outcome) -> None:
        self._key, self._outcome = key, outcome


_PREVIEWS = _PreviewCache()


@command("regions.segment", lane=True, exclusive=True)
def regions_segment(ctx: JobContext, params: SegmentParams) -> SegmentResult:
    """Split the scan (or the given faces) into regions of single primitives.

    With `dry_run` the document is unchanged. The commit replaces the labels of
    the segmented faces; a new region that overlaps an old one by more than half
    keeps its id, name and colour.
    """
    session = ctx.session
    document = session.document
    mesh = _current_mesh(ctx, params.scan_key)
    faces = None if params.faces is None else _face_indices(params.faces, mesh)
    if faces is not None and len(faces) == 0:
        raise KernelError(ErrorCode.EMPTY_SELECTION)
    key = _segment_key(mesh, document, params, faces)
    outcome = _PREVIEWS.get(key)
    if outcome is None:
        outcome = _segment(ctx, mesh, document, params, faces, key)
        _PREVIEWS.put(key, outcome)
    if params.dry_run:
        return SegmentResult(
            regions=outcome.found,
            labels=outcome.labels,
            color_index=_color_table(outcome.regions.items),
            revision=None,
        )
    updated = replace(document, next_id=outcome.next_id)
    revision = _commit(ctx, updated, outcome.regions, outcome.labels, "segment")
    return SegmentResult(regions=outcome.found, labels=None, color_index=None, revision=revision)


def _segment_key(
    mesh: EvalMesh, document: Document, params: SegmentParams, faces: FaceIndices | None
) -> str:
    digest = hashlib.sha256()
    digest.update(mesh.key.encode("utf-8"))
    digest.update(str(document.regions.labels).encode("utf-8"))
    digest.update(repr((document.next_id, params.sensitivity, params.min_area)).encode("utf-8"))
    digest.update(repr(sorted((item.id, item.label) for item in document.regions.items)).encode())
    if faces is not None:
        digest.update(np.ascontiguousarray(faces).tobytes())
    return digest.hexdigest()


def _segment(
    ctx: JobContext,
    mesh: EvalMesh,
    document: Document,
    params: SegmentParams,
    faces: FaceIndices | None,
    key: str,
) -> _Outcome:
    scan = document.scan
    assert scan is not None
    lod = LEVELS_OF_DETAIL.get(mesh, scan.key, ctx.session.built(ctx).result.matrix, ctx)
    result = segment(
        mesh,
        lod,
        params.sensitivity,
        params.min_area,
        ctx,
        seeded_rng(f"regions.segment:{key}"),
        faces,
    )
    ctx.check_cancelled()
    found_count = len(result.kinds)
    old_labels = _labels(ctx, document)
    inside = np.ones(len(mesh.faces), dtype=bool) if faces is None else _mask(faces, mesh)

    # old regions with faces outside the segmented set keep those faces and their label;
    # an old region that a new one replaces lends it its label, id, name and colour
    kept_labels = np.where(inside, 0, old_labels).astype(np.uint16)
    surviving = set(np.unique(kept_labels).tolist()) - {0}
    matches = match_regions(old_labels, result.labels)
    replaced = set(matches.values())
    fresh = free_labels(surviving | replaced, found_count - len(matches), MAX_REGIONS)
    if fresh is None:
        raise KernelError(ErrorCode.TOO_MANY_REGIONS, {"max": MAX_REGIONS})
    unused = iter(fresh)
    value_of = np.zeros(found_count + 1, dtype=np.uint16)
    for found in range(1, found_count + 1):
        value_of[found] = matches[found] if found in matches else next(unused)
    labels = np.where(result.labels > 0, value_of[result.labels], kept_labels).astype(np.uint16)

    by_label = {item.label: item for item in document.regions.items}
    items = [
        item
        for item in document.regions.items
        if item.label in surviving and item.label not in replaced
    ]
    next_id = document.next_id
    for found in range(1, found_count + 1):
        previous = by_label.get(matches[found]) if found in matches else None
        if previous is None:
            region_id, name, color = f"r{next_id}", None, -1
            next_id += 1
        else:
            region_id, name, color = previous.id, previous.name, previous.color_index
        items.append(
            Region(
                id=region_id,
                label=int(value_of[found]),
                name=name,
                kind=result.kinds[found - 1],
                rms=result.rms[found - 1],
                face_count=0,
                area=0.0,
                color_index=color,
            )
        )
    regions = _finish(mesh, labels, items)
    final = {item.label: item for item in regions.items}
    found_regions = [
        SegmentedRegion(
            label=int(value_of[found]),
            kind=result.kinds[found - 1],
            rms=result.rms[found - 1],
            face_count=final[int(value_of[found])].face_count,
            area=final[int(value_of[found])].area,
            color_index=final[int(value_of[found])].color_index,
        )
        for found in range(1, found_count + 1)
    ]
    return _Outcome(regions=regions, labels=labels, found=found_regions, next_id=next_id)


# --------------------------------------------------------------------------- edit


@dataclass(frozen=True)
class CreateParams:
    scan_key: str
    faces: U32Array


@dataclass(frozen=True)
class RegionEditResult:
    region_id: str | None
    """The created or surviving region; null after a deletion."""
    revision: int


@command("regions.create")
def regions_create(ctx: JobContext, params: CreateParams) -> RegionEditResult:
    """Make a region of the given faces; they leave the regions they belonged to."""
    document = ctx.session.document
    mesh = _current_mesh(ctx, params.scan_key)
    faces = _face_indices(params.faces, mesh)
    if len(faces) == 0:
        raise KernelError(ErrorCode.EMPTY_SELECTION)
    labels = _labels(ctx, document)
    fresh = free_labels({item.label for item in document.regions.items}, 1, MAX_REGIONS)
    if fresh is None:
        raise KernelError(ErrorCode.TOO_MANY_REGIONS, {"max": MAX_REGIONS})
    labels[faces] = fresh[0]
    kind, rms = _classify(mesh, faces, f"regions.create:{mesh.key}")
    region_id = f"r{document.next_id}"
    created = Region(region_id, fresh[0], None, kind, rms, 0, 0.0, -1)
    regions = _finish(mesh, labels, [*document.regions.items, created])
    updated = replace(document, regions=regions, next_id=document.next_id + 1)
    revision = _commit(ctx, updated, regions, labels, "createRegion")
    return RegionEditResult(region_id=region_id, revision=revision)


@dataclass(frozen=True)
class RegionRename:
    name: str | None
    """null (or an empty name) restores the default name."""


@dataclass(frozen=True)
class UpdateParams:
    region_id: str
    scan_key: str
    add_faces: U32Array | None = None
    remove_faces: U32Array | None = None
    rename: RegionRename | None = None


@command("regions.update")
def regions_update(ctx: JobContext, params: UpdateParams) -> RegionEditResult:
    """Add faces to a region (taking them from others), remove faces, or rename it."""
    document = ctx.session.document
    mesh = _current_mesh(ctx, params.scan_key)
    region = _region(document, params.region_id)
    labels = _labels(ctx, document)
    changed_faces = False
    if params.add_faces is not None:
        labels[_face_indices(params.add_faces, mesh)] = region.label
        changed_faces = True
    if params.remove_faces is not None:
        removed = _face_indices(params.remove_faces, mesh)
        removed = removed[labels[removed] == region.label]
        labels[removed] = 0
        changed_faces = True
    if params.rename is not None:
        name = (params.rename.name or "").strip()
        region = replace(region, name=name or None)
    if changed_faces:
        members = np.nonzero(labels == region.label)[0]
        kind, rms = _classify(mesh, members, f"regions.update:{mesh.key}:{region.id}")
        region = replace(region, kind=kind, rms=rms)
    items = [region if item.id == region.id else item for item in document.regions.items]
    regions = _finish(mesh, labels, items)
    updated = replace(document, regions=regions)
    survivor = region.id if any(item.id == region.id for item in regions.items) else None
    revision = _commit(ctx, updated, regions, labels, "updateRegion")
    return RegionEditResult(region_id=survivor, revision=revision)


@dataclass(frozen=True)
class MergeParams:
    region_ids: list[str]


@command("regions.merge")
def regions_merge(ctx: JobContext, params: MergeParams) -> RegionEditResult:
    """Join regions into the largest of them, which keeps its id, name and colour."""
    document = ctx.session.document
    ids = list(dict.fromkeys(params.region_ids))
    if len(ids) < 2:
        raise KernelError(ErrorCode.MERGE_NEEDS_TWO, {"count": len(ids)})
    mesh = _current_mesh(ctx, None)
    merging = [_region(document, region_id) for region_id in ids]
    survivor = max(merging, key=lambda item: item.face_count)
    labels = _labels(ctx, document)
    labels[np.isin(labels, [item.label for item in merging])] = survivor.label
    members = np.nonzero(labels == survivor.label)[0]
    kind, rms = _classify(mesh, members, f"regions.merge:{mesh.key}:{survivor.id}")
    merged = replace(survivor, kind=kind, rms=rms)
    items = [
        merged if item.id == survivor.id else item
        for item in document.regions.items
        if item.id == survivor.id or item.id not in ids
    ]
    regions = _finish(mesh, labels, items)
    revision = _commit(ctx, replace(document, regions=regions), regions, labels, "mergeRegions")
    return RegionEditResult(region_id=survivor.id, revision=revision)


@dataclass(frozen=True)
class DeleteParams:
    region_ids: list[str]


@command("regions.delete")
def regions_delete(ctx: JobContext, params: DeleteParams) -> RegionEditResult:
    """Remove regions; their faces become unassigned."""
    document = ctx.session.document
    mesh = _current_mesh(ctx, None)
    removing = [_region(document, region_id) for region_id in dict.fromkeys(params.region_ids)]
    labels = _labels(ctx, document)
    labels[np.isin(labels, [item.label for item in removing])] = 0
    removed_ids = {item.id for item in removing}
    items = [item for item in document.regions.items if item.id not in removed_ids]
    regions = _finish(mesh, labels, items)
    revision = _commit(ctx, replace(document, regions=regions), regions, labels, "deleteRegions")
    return RegionEditResult(region_id=None, revision=revision)


# --------------------------------------------------------------------------- helpers


def _current_mesh(ctx: JobContext, scan_key: str | None) -> EvalMesh:
    """The aligned working mesh; `scan_key` must name the current scan when given."""
    session = ctx.session
    scan = session.document.scan
    if scan is None:
        raise KernelError(ErrorCode.NO_SCAN)
    if scan_key is not None and scan_key != scan.key:
        raise KernelError(ErrorCode.STALE_SCAN, {"scanKey": scan_key})
    mesh = session.built(ctx).result.mesh
    if mesh is None:
        raise KernelError(ErrorCode.NO_SCAN)
    return mesh


def _face_indices(faces: npt.NDArray[np.uint32], mesh: EvalMesh) -> FaceIndices:
    indices = np.unique(np.asarray(faces, dtype=np.int64))
    if len(indices) and indices[-1] >= len(mesh.faces):
        raise KernelError(ErrorCode.INVALID_FACE, {"face": int(indices[-1])})
    return indices


def _mask(faces: FaceIndices, mesh: EvalMesh) -> npt.NDArray[np.bool_]:
    mask = np.zeros(len(mesh.faces), dtype=bool)
    mask[faces] = True
    return mask


def _labels(ctx: JobContext, document: Document) -> LabelArray:
    """A writable copy of the region labels (all zero when there are no regions yet)."""
    scan = document.scan
    assert scan is not None
    ref = document.regions.labels
    if ref is None:
        return np.zeros(scan.face_count, dtype=np.uint16)
    return ctx.session.blobs.get(ref).astype(np.uint16, copy=True)


def _region(document: Document, region_id: str) -> Region:
    region = next((item for item in document.regions.items if item.id == region_id), None)
    if region is None:
        raise KernelError(ErrorCode.UNKNOWN_REGION, {"region": region_id})
    return region


def _classify(mesh: EvalMesh, faces: FaceIndices, seed: str) -> tuple[RegionKind, float | None]:
    kind, rms = classify_faces(mesh, faces, seeded_rng(seed))
    return (kind or "unknown"), rms


def _finish(mesh: EvalMesh, labels: LabelArray, items: Sequence[Region]) -> Regions:
    """Region items with current face counts and areas and valid colours; empty ones dropped.

    Colours of existing regions are kept unless a larger neighbour has the same
    one; new regions (colour -1) get the colour that differs most from their
    neighbours'.
    """
    highest = max((item.label for item in items), default=0)
    counts, areas = label_sizes(labels, mesh.face_areas, highest)
    alive = [item for item in items if counts[item.label] > 0]
    existing = {item.label: item.color_index for item in alive if item.color_index >= 0}
    sizes = {item.label: float(areas[item.label]) for item in alive}
    colors = assign_colors(sizes.keys(), adjacency(labels, mesh.face_graph.pairs), existing, sizes)
    updated = tuple(
        replace(
            item,
            face_count=int(counts[item.label]),
            area=float(areas[item.label]),
            color_index=colors[item.label],
        )
        for item in alive
    )
    return Regions(labels=None, items=updated)


def _commit(
    ctx: JobContext, document: Document, regions: Regions, labels: LabelArray, label: str
) -> int:
    ref = ctx.session.blobs.put(labels) if regions.items else None
    final = replace(document, regions=replace(regions, labels=ref))
    return ctx.session.commit(final, label, ctx).revision


def _color_table(items: Sequence[Region]) -> npt.NDArray[np.uint8]:
    """Palette index per label value, as in the regions scene payload."""
    highest = max((item.label for item in items), default=0)
    table = np.zeros(highest + 1, dtype=np.uint8)
    for item in items:
        table[item.label] = item.color_index
    return table
