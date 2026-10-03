"""The scene manifest and the display payloads behind it.

After every commit the renderer receives a manifest: the scan, the region
labels and one item per drawable (body faces, body edges, construction
geometry, sketches). Items are identified by keys derived from result keys and
tessellation settings, never from array contents, so equal inputs always give
equal keys. The renderer fetches the payloads it does not have yet with
`scene.fetch`; payloads are built on first request and cached.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Literal

import numpy as np

from m2c_kernel.cad.deflection import DISPLAY_ANGULAR_DEFLECTION_RAD, DISPLAY_LINEAR_DEFLECTION_MM
from m2c_kernel.document.model import Document
from m2c_kernel.document.results import Body, DisplayKind, DisplaySource, DisplayStyle
from m2c_kernel.geometry import Matrix4, Vec3
from m2c_kernel.protocol.wire import F32Array, U8Array, U16Array, U32Array
from m2c_kernel.session.blobs import BlobStore

if TYPE_CHECKING:
    from m2c_kernel.cad.tessellate import Tessellation

TESSELLATION_KEY = f"t{DISPLAY_LINEAR_DEFLECTION_MM:g}-{DISPLAY_ANGULAR_DEFLECTION_RAD:g}"


@dataclass(frozen=True)
class SceneItem:
    key: str
    kind: DisplayKind
    style: DisplayStyle
    owner: str
    body_id: str | None = None


@dataclass(frozen=True)
class SceneScan:
    """The scan as drawn: `positions` are relative to `origin` in scan coordinates.

    The renderer places them with `transform` (scan to part coordinates), so a
    new alignment never resends the scan. `scan_key` equals `Scan.key`.
    """

    key: str
    scan_key: str
    origin: Vec3
    transform: Matrix4
    face_count: int
    vertex_count: int


@dataclass(frozen=True)
class SceneManifest:
    scan: SceneScan | None
    regions: str | None
    items: tuple[SceneItem, ...]


@dataclass(frozen=True, kw_only=True)
class ScanPayload:
    type: Literal["scan"] = "scan"
    key: str
    positions: F32Array
    indices: U32Array
    normals: F32Array


@dataclass(frozen=True, kw_only=True)
class MeshPayload:
    """Triangles in part coordinates; `face_ids` is the B-Rep face of each triangle."""

    type: Literal["mesh"] = "mesh"
    key: str
    positions: F32Array
    indices: U32Array
    normals: F32Array
    face_ids: U32Array


@dataclass(frozen=True, kw_only=True)
class LinesPayload:
    """Line segments (s, 2, 3) in part coordinates with an id per segment (edge or entity).

    For body edges, `faces` (s, 2) holds the B-Rep faces on both sides of each segment's
    edge, as indices into the body's `face_tags`.
    """

    type: Literal["lines"] = "lines"
    key: str
    segments: F32Array
    ids: U32Array
    faces: U32Array | None = None


@dataclass(frozen=True, kw_only=True)
class PointsPayload:
    type: Literal["points"] = "points"
    key: str
    positions: F32Array


@dataclass(frozen=True, kw_only=True)
class RegionsPayload:
    """One label per scan face (0 = unassigned) and a palette index per label."""

    type: Literal["regions"] = "regions"
    key: str
    labels: U16Array
    color_index: U8Array


type ScenePayload = ScanPayload | MeshPayload | LinesPayload | PointsPayload | RegionsPayload
type PayloadFactory = Callable[[], ScenePayload]


class SceneStore:
    """Payload factories by key; a payload is built on its first fetch and then cached."""

    def __init__(self, max_factories: int = 4096, max_payload_bytes: int = 512 << 20) -> None:
        self._factories: OrderedDict[str, PayloadFactory] = OrderedDict()
        self._payloads: OrderedDict[str, tuple[ScenePayload, int]] = OrderedDict()
        self._max_factories = max_factories
        self._max_bytes = max_payload_bytes
        self._bytes = 0

    def register(self, key: str, factory: PayloadFactory) -> None:
        self._factories[key] = factory
        self._factories.move_to_end(key)
        while len(self._factories) > self._max_factories:
            self._factories.popitem(last=False)

    def fetch(self, key: str) -> ScenePayload | None:
        cached = self._payloads.get(key)
        if cached is not None:
            self._payloads.move_to_end(key)
            return cached[0]
        factory = self._factories.get(key)
        if factory is None:
            return None
        payload = factory()
        size = _payload_bytes(payload)
        self._payloads[key] = (payload, size)
        self._bytes += size
        while self._bytes > self._max_bytes and len(self._payloads) > 1:
            _, (_, evicted) = self._payloads.popitem(last=False)
            self._bytes -= evicted
        return payload


def _payload_bytes(payload: ScenePayload) -> int:
    arrays = [value for value in vars(payload).values() if isinstance(value, np.ndarray)]
    return sum(array.nbytes for array in arrays)


def build_scene(
    document: Document,
    matrix: Matrix4,
    bodies: dict[str, Body],
    body_keys: dict[str, str],
    body_owner: dict[str, str],
    sources: dict[str, tuple[str, tuple[DisplaySource, ...]]],
    blobs: BlobStore,
    store: SceneStore,
) -> SceneManifest:
    """Register payload factories for everything visible and return the manifest.

    `sources` maps a feature id to its result key and display sources.
    """
    scan_entry = None
    if document.scan is not None:
        scan = document.scan
        scan_payload_key = f"{scan.key}:s{scan.display_smoothing}"
        store.register(scan_payload_key, _scan_factory(scan_payload_key, document, blobs))
        scan_entry = SceneScan(
            key=scan_payload_key,
            scan_key=scan.key,
            origin=scan.origin,
            transform=matrix,
            face_count=scan.face_count,
            vertex_count=scan.vertex_count,
        )

    regions_key = None
    if document.regions.labels is not None:
        regions_key = f"regions:{document.regions.labels}"
        store.register(regions_key, _regions_factory(regions_key, document, blobs))

    items: list[SceneItem] = []
    for body_id, body in bodies.items():
        items += register_body(body_id, body, body_keys[body_id], body_owner[body_id], store)
    for feature_id, (result_key, feature_sources) in sources.items():
        items += register_sources(feature_id, result_key, feature_sources, store)
    return SceneManifest(scan=scan_entry, regions=regions_key, items=tuple(items))


def register_body(
    body_id: str,
    body: Body,
    body_key: str,
    owner: str,
    store: SceneStore,
    face_style: DisplayStyle = "body",
) -> list[SceneItem]:
    """Register the face and edge payloads of a body; returns their scene items."""
    base = f"body:{body_key}:{TESSELLATION_KEY}"
    mesh_factory, lines_factory = _body_factories(base, body)
    store.register(f"{base}:faces", mesh_factory)
    store.register(f"{base}:edges", lines_factory)
    return [
        SceneItem(f"{base}:faces", "mesh", face_style, owner, body_id),
        SceneItem(f"{base}:edges", "lines", "bodyEdges", owner, body_id),
    ]


def register_sources(
    feature_id: str, result_key: str, sources: tuple[DisplaySource, ...], store: SceneStore
) -> list[SceneItem]:
    """Register the display sources of one feature result; returns their scene items."""
    items = []
    for index, source in enumerate(sources):
        key = f"src:{result_key}:{index}"
        store.register(key, _source_factory(key, source))
        items.append(SceneItem(key, source.kind, source.style, feature_id))
    return items


def _scan_factory(key: str, document: Document, blobs: BlobStore) -> PayloadFactory:
    scan = document.scan
    assert scan is not None

    def build() -> ScenePayload:
        from m2c_kernel.mesh.normals import vertex_normals
        from m2c_kernel.mesh.smoothing import taubin

        positions = blobs.get(scan.vertices)
        faces = blobs.get(scan.faces).astype(np.int64)
        points = taubin(positions.astype(np.float64), faces, scan.display_smoothing)
        normals = vertex_normals(points, faces)
        return ScanPayload(
            key=key,
            positions=points.astype(np.float32),
            indices=faces.astype(np.uint32),
            normals=normals.astype(np.float32),
        )

    return build


def _regions_factory(key: str, document: Document, blobs: BlobStore) -> PayloadFactory:
    regions = document.regions
    labels_ref = regions.labels
    assert labels_ref is not None

    def build() -> ScenePayload:
        labels = blobs.get(labels_ref).astype(np.uint16)
        highest = max((item.label for item in regions.items), default=0)
        color_index = np.zeros(highest + 1, dtype=np.uint8)
        for item in regions.items:
            color_index[item.label] = item.color_index
        return RegionsPayload(key=key, labels=labels, color_index=color_index)

    return build


def _body_factories(base: str, body: Body) -> tuple[PayloadFactory, PayloadFactory]:
    @cache
    def tessellation() -> Tessellation:
        from m2c_kernel.cad.tessellate import tessellate

        return tessellate(body.shape)

    def faces() -> ScenePayload:
        mesh = tessellation()
        from m2c_kernel.mesh.normals import vertex_normals

        normals = (
            vertex_normals(mesh.vertices, mesh.triangles) if len(mesh.triangles) else mesh.vertices
        )
        return MeshPayload(
            key=f"{base}:faces",
            positions=mesh.vertices.astype(np.float32),
            indices=mesh.triangles.astype(np.uint32),
            normals=np.asarray(normals, dtype=np.float32),
            face_ids=mesh.triangle_faces,
        )

    def edges() -> ScenePayload:
        mesh = tessellation()
        return LinesPayload(
            key=f"{base}:edges",
            segments=mesh.edge_segments.astype(np.float32),
            ids=mesh.segment_edges,
            faces=mesh.segment_faces,
        )

    return faces, edges


def _source_factory(key: str, source: DisplaySource) -> PayloadFactory:
    def build() -> ScenePayload:
        positions = source.positions.astype(np.float32)
        if source.kind == "mesh":
            assert source.indices is not None
            from m2c_kernel.mesh.normals import vertex_normals

            normals = vertex_normals(source.positions, source.indices)
            face_ids = np.zeros(len(source.indices), dtype=np.uint32)
            return MeshPayload(
                key=key,
                positions=positions,
                indices=source.indices.astype(np.uint32),
                normals=normals.astype(np.float32),
                face_ids=face_ids,
            )
        if source.kind == "lines":
            ids = (
                source.ids if source.ids is not None else np.arange(len(positions), dtype=np.uint32)
            )
            return LinesPayload(key=key, segments=positions, ids=ids.astype(np.uint32))
        return PointsPayload(key=key, positions=positions)

    return build
