// The scan as non-indexed triangles: face i owns vertices 3i..3i+2. WebGL 2 has
// no gl_PrimitiveID, so per-face state is a per-vertex attribute; de-indexing
// makes it exact and keeps face indices identical to the kernel's. The faces are
// drawn in chunks of CHUNK_FACES whose buffers are views into one array each, so
// uploads spread over frames and a brush stroke re-uploads only touched ranges.

import * as THREE from 'three';
import { MeshBVH } from 'three-mesh-bvh';

import { CHUNK_FACES, type PreparedGeometry } from './workers/meshPrep';
import type { PreparedScanTopology, ScanPreparation } from './workers/scanWorkers';
import { NO_DEVIATION } from './scanMaterial';

export const FLAG_SELECTED = 1;
export const FLAG_HOVER = 2;
export const FLAG_HIDDEN = 4;
const STATE_SHIFT = 3;
const STATE_MASK = 3 << STATE_SHIFT;

interface Chunk {
  start: number;
  count: number;
  geometry: THREE.BufferGeometry;
  flags: THREE.BufferAttribute;
  mesh: THREE.Mesh | null;
  /** A full flag upload is queued; ranges added now would shrink it. */
  fullUpload: boolean;
}

export interface ScanTopologyState {
  centroids: Float32Array;
  faceNormals: Float32Array;
  neighbours: Int32Array;
  indices: Uint32Array;
  bvh: MeshBVH;
}

/** One displayed scan: its buffers, per-face state and draw chunks. */
export class ScanMesh {
  /** Chunk meshes; they join as their buffers are uploaded. */
  readonly group = new THREE.Group();
  readonly faceCount: number;
  /** Scan-local bounds. */
  readonly bounds: THREE.Box3;
  /** De-indexed corner positions (9 floats per face), scan-local. */
  readonly positions: Float32Array;
  topology: ScanTopologyState | null = null;
  private readonly flags: Uint8Array;
  private regionLabels: Uint16Array | null = null;
  private deviation: Float32Array | null = null;
  private readonly chunks: Chunk[] = [];
  private material: THREE.Material;

  constructor(
    /** Key of the drawn payload (changes with display smoothing). */
    readonly displayKey: string,
    /** `Scan.key`; per-face state belongs to it. */
    readonly scanKey: string,
    geometry: PreparedGeometry,
    readonly preparation: ScanPreparation,
    material: THREE.Material,
  ) {
    this.faceCount = geometry.positions.length / 9;
    this.positions = geometry.positions;
    this.material = material;
    this.flags = new Uint8Array(this.faceCount * 3);
    const b = geometry.bounds;
    const total = b.length - 6;
    this.bounds = new THREE.Box3(
      new THREE.Vector3(b[total], b[total + 1], b[total + 2]),
      new THREE.Vector3(b[total + 3], b[total + 4], b[total + 5]),
    );
    for (let start = 0, index = 0; start < this.faceCount; start += CHUNK_FACES, index += 1) {
      const count = Math.min(CHUNK_FACES, this.faceCount - start);
      const chunkGeometry = new THREE.BufferGeometry();
      chunkGeometry.setAttribute(
        'position',
        new THREE.BufferAttribute(this.positions.subarray(start * 9, (start + count) * 9), 3),
      );
      chunkGeometry.setAttribute(
        'normal',
        new THREE.BufferAttribute(
          geometry.normals.subarray(start * 12, (start + count) * 12),
          4,
          true,
        ),
      );
      const flags = new THREE.BufferAttribute(
        this.flags.subarray(start * 3, (start + count) * 3),
        1,
        true,
      );
      flags.setUsage(THREE.DynamicDrawUsage);
      chunkGeometry.setAttribute('aFlags', flags);
      const o = index * 6;
      chunkGeometry.boundingBox = new THREE.Box3(
        new THREE.Vector3(b[o], b[o + 1], b[o + 2]),
        new THREE.Vector3(b[o + 3], b[o + 4], b[o + 5]),
      );
      chunkGeometry.boundingSphere = chunkGeometry.boundingBox.getBoundingSphere(
        new THREE.Sphere(),
      );
      this.chunks.push({
        start,
        count,
        geometry: chunkGeometry,
        flags,
        mesh: null,
        fullUpload: false,
      });
    }
  }

  get chunkCount(): number {
    return this.chunks.length;
  }

  /** Geometry of each chunk and the index of its first face (for the face-id pass). */
  *chunkGeometries(): Generator<{ geometry: THREE.BufferGeometry; start: number }> {
    for (const chunk of this.chunks) if (chunk.mesh) yield chunk;
  }

  /** Faces in chunks that are part of the scene. */
  get shownFaces(): number {
    return this.chunks.reduce((sum, chunk) => sum + (chunk.mesh ? chunk.count : 0), 0);
  }

  get complete(): boolean {
    return this.chunks.every((chunk) => chunk.mesh);
  }

  /** Adds the next chunk to the scene (its buffers upload with the next frame). */
  showNextChunk(): boolean {
    const chunk = this.chunks.find((candidate) => !candidate.mesh);
    if (!chunk) return false;
    chunk.mesh = new THREE.Mesh(chunk.geometry, this.material);
    chunk.mesh.matrixAutoUpdate = false;
    chunk.mesh.raycast = () => undefined;
    this.group.add(chunk.mesh);
    return true;
  }

  setMaterial(material: THREE.Material): void {
    this.material = material;
    for (const chunk of this.chunks) if (chunk.mesh) chunk.mesh.material = material;
  }

  attachTopology(topology: PreparedScanTopology): void {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    const bvh = MeshBVH.deserialize(topology.bvh, geometry, { setIndex: false });
    this.topology = { ...topology, bvh };
  }

  dispose(): void {
    this.preparation.dispose();
    for (const chunk of this.chunks) chunk.geometry.dispose();
    this.group.clear();
  }

  // Per-face state --------------------------------------------------------------

  flagOf(face: number): number {
    return this.flags[face * 3] ?? 0;
  }

  isHidden(face: number): boolean {
    return (this.flagOf(face) & FLAG_HIDDEN) !== 0;
  }

  /** One byte per face, 1 = hidden; null when nothing is hidden. */
  hiddenMask(): Uint8Array | null {
    let any = false;
    const mask = new Uint8Array(this.faceCount);
    for (let face = 0; face < this.faceCount; face += 1) {
      if (this.flags[face * 3]! & FLAG_HIDDEN) {
        mask[face] = 1;
        any = true;
      }
    }
    return any ? mask : null;
  }

  /** Sets or clears `flag` on the faces where `on(face)` says so, for every face. */
  setFlagForAll(flag: number, on: (face: number) => boolean): void {
    for (let face = 0; face < this.faceCount; face += 1) this.writeFlag(face, flag, on(face));
    this.uploadAllFlags();
  }

  setFlagForFaces(faces: ArrayLike<number>, flag: number, on: boolean): void {
    const touched = new Map<Chunk, [number, number]>();
    for (let i = 0; i < faces.length; i += 1) {
      const face = faces[i] ?? -1;
      if (face < 0 || face >= this.faceCount) continue;
      this.writeFlag(face, flag, on);
      const chunk = this.chunks[Math.floor(face / CHUNK_FACES)];
      if (!chunk) continue;
      const range = touched.get(chunk);
      if (range) {
        range[0] = Math.min(range[0], face);
        range[1] = Math.max(range[1], face);
      } else {
        touched.set(chunk, [face, face]);
      }
    }
    for (const [chunk, [first, last]] of touched) {
      if (!chunk.fullUpload)
        chunk.flags.addUpdateRange((first - chunk.start) * 3, (last - first + 1) * 3);
      chunk.flags.needsUpdate = true;
    }
  }

  /** Pass/fail state (0-3) of the given faces. */
  setStates(faces: ArrayLike<number>, states: ArrayLike<number> | null): void {
    for (let i = 0; i < faces.length; i += 1) {
      const face = faces[i] ?? -1;
      if (face < 0 || face >= this.faceCount) continue;
      const offset = face * 3;
      const state = ((states?.[i] ?? 0) & 3) << STATE_SHIFT;
      const next = ((this.flags[offset] ?? 0) & ~STATE_MASK) | state;
      this.flags.fill(next, offset, offset + 3);
    }
    this.uploadAllFlags();
  }

  /** Region label per face; null removes the attribute data (all unassigned). */
  setRegionLabels(labels: Uint16Array | null): void {
    if (!labels && !this.regionLabels) return;
    if (!this.regionLabels) {
      this.regionLabels = new Uint16Array(this.faceCount * 3);
      this.addChunkAttribute('aRegion', this.regionLabels, 3);
    }
    const target = this.regionLabels;
    for (let face = 0; face < this.faceCount; face += 1) {
      const label = labels?.[face] ?? 0;
      target[face * 3] = label;
      target[face * 3 + 1] = label;
      target[face * 3 + 2] = label;
    }
    this.markChunkAttribute('aRegion');
  }

  /** Signed distance per scan vertex (NaN = no data), spread to the face corners. */
  setDeviation(values: Float32Array | null): boolean {
    const indices = this.topology?.indices;
    if (!indices) return false;
    if (!values && !this.deviation) return true;
    if (!this.deviation) {
      this.deviation = new Float32Array(this.faceCount * 3);
      this.addChunkAttribute('aDeviation', this.deviation, 3);
    }
    const target = this.deviation;
    for (let corner = 0; corner < indices.length; corner += 1) {
      const value = values ? (values[indices[corner] ?? 0] ?? Number.NaN) : Number.NaN;
      target[corner] = Number.isFinite(value) ? value : NO_DEVIATION;
    }
    this.markChunkAttribute('aDeviation');
    return true;
  }

  /** Copies all per-face state from a mesh of the same scan (display smoothing changed). */
  copyStateFrom(previous: ScanMesh): void {
    if (previous.faceCount !== this.faceCount) return;
    this.flags.set(previous.flags);
    this.uploadAllFlags();
    if (previous.regionLabels) {
      this.regionLabels = previous.regionLabels.slice();
      this.addChunkAttribute('aRegion', this.regionLabels, 3);
    }
    if (previous.deviation) {
      this.deviation = previous.deviation.slice();
      this.addChunkAttribute('aDeviation', this.deviation, 3);
    }
  }

  /** Scan-local bounds of the visible selected faces, or null. */
  selectionBounds(): THREE.Box3 | null {
    const box = new THREE.Box3();
    const point = new THREE.Vector3();
    for (let face = 0; face < this.faceCount; face += 1) {
      if (((this.flags[face * 3] ?? 0) & (FLAG_SELECTED | FLAG_HIDDEN)) !== FLAG_SELECTED) continue;
      for (let corner = 0; corner < 3; corner += 1)
        box.expandByPoint(point.fromArray(this.positions, face * 9 + corner * 3));
    }
    return box.isEmpty() ? null : box;
  }

  /** Called after each rendered frame: queued uploads have happened. */
  afterRender(): void {
    for (const chunk of this.chunks) chunk.fullUpload = false;
  }

  private writeFlag(face: number, flag: number, on: boolean): void {
    const offset = face * 3;
    const current = this.flags[offset] ?? 0;
    const next = on ? current | flag : current & ~flag;
    if (next !== current) this.flags.fill(next, offset, offset + 3);
  }

  private uploadAllFlags(): void {
    for (const chunk of this.chunks) {
      chunk.flags.clearUpdateRanges();
      chunk.flags.needsUpdate = true;
      chunk.fullUpload = true;
    }
  }

  private addChunkAttribute(name: string, array: Uint16Array | Float32Array, perFace: number) {
    const normalized = array instanceof Uint16Array;
    for (const chunk of this.chunks) {
      const view = array.subarray(chunk.start * perFace, (chunk.start + chunk.count) * perFace);
      chunk.geometry.setAttribute(name, new THREE.BufferAttribute(view, 1, normalized));
    }
  }

  private markChunkAttribute(name: string): void {
    for (const chunk of this.chunks) {
      const attribute = chunk.geometry.getAttribute(name) as THREE.BufferAttribute | undefined;
      if (attribute) attribute.needsUpdate = true;
    }
  }
}
