// Scan-face queries that do not need the renderer: polygon picking, face
// adjacency and the ScanView proxy used before a scan is loaded.

import * as THREE from 'three';

import type { DeviationDisplay, ScanTopology, ScanView } from './api';
import type { ScanMesh } from './scanMesh';

/** Delegates to the current scan mesh; does nothing while no scan is loaded. */
export class ScanProxy implements ScanView {
  constructor(private readonly current: () => ScanMesh | null) {}

  get faceCount(): number {
    return this.current()?.faceCount ?? 0;
  }

  get scanKey(): string | null {
    return this.current()?.scanKey ?? null;
  }

  setSelection(mask: Uint8Array): void {
    this.current()?.setSelection(mask);
  }

  updateSelection(faces: Uint32Array, selected: boolean): void {
    this.current()?.updateSelection(faces, selected);
  }

  setHover(faces: Uint32Array | null): void {
    this.current()?.setHover(faces);
  }

  setHidden(mask: Uint8Array | null): void {
    this.current()?.setHidden(mask);
  }

  setFaceStates(faces: Uint32Array | null, states?: Uint8Array): void {
    this.current()?.setFaceStates(faces, states);
  }

  setRegions(labels: Uint16Array | null, colorIndex: Uint8Array | null): void {
    this.current()?.setRegions(labels, colorIndex);
  }

  setDeviation(values: Float32Array | null, display?: DeviationDisplay): void {
    this.current()?.setDeviation(values, display);
  }

  setOpacity(opacity: number): void {
    this.current()?.setOpacity(opacity);
  }
}

function insidePolygon(x: number, y: number, polygon: Float32Array): boolean {
  let inside = false;
  const count = polygon.length / 2;
  for (let i = 0, j = count - 1; i < count; j = i, i += 1) {
    const xi = polygon[i * 2] ?? 0;
    const yi = polygon[i * 2 + 1] ?? 0;
    const xj = polygon[j * 2] ?? 0;
    const yj = polygon[j * 2 + 1] ?? 0;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * Faces whose centroid projects within `radius` pixels of a screen point (brush).
 * With `toView`, faces turned away from the camera are skipped; faces hidden
 * behind other geometry are not detected here (a face-id render pass does that).
 */
export function facesInCircle(
  mesh: ScanMesh,
  at: { x: number; y: number },
  radius: number,
  size: { width: number; height: number },
  toClip: THREE.Matrix4,
  toView: THREE.Matrix3 | null,
): Uint32Array {
  const point = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const radiusSquared = radius * radius;
  const result: number[] = [];
  for (let face = 0; face < mesh.faceCount; face += 1) {
    point.fromArray(mesh.centroids, face * 3).applyMatrix4(toClip);
    const dx = ((point.x + 1) / 2) * size.width - at.x;
    const dy = ((1 - point.y) / 2) * size.height - at.y;
    if (dx * dx + dy * dy > radiusSquared || mesh.isHidden(face)) continue;
    if (toView && normal.fromArray(mesh.faceNormals, face * 3).applyMatrix3(toView).z <= 0)
      continue;
    result.push(face);
  }
  return Uint32Array.from(result);
}

/**
 * Faces whose centroid projects inside a screen polygon (x, y pairs in CSS px).
 * With `toView`, faces turned away from the camera are skipped.
 */
export function facesInPolygon(
  mesh: ScanMesh,
  polygon: Float32Array,
  size: { width: number; height: number },
  toClip: THREE.Matrix4,
  toView: THREE.Matrix3 | null,
): Uint32Array {
  const point = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const result: number[] = [];
  for (let face = 0; face < mesh.faceCount; face += 1) {
    if (mesh.isHidden(face)) continue;
    if (toView && normal.fromArray(mesh.faceNormals, face * 3).applyMatrix3(toView).z <= 0)
      continue;
    point.fromArray(mesh.centroids, face * 3).applyMatrix4(toClip);
    const x = ((point.x + 1) / 2) * size.width;
    const y = ((1 - point.y) / 2) * size.height;
    if (insidePolygon(x, y, polygon)) result.push(face);
  }
  return Uint32Array.from(result);
}

/** Face adjacency across shared edges and centroids in part coordinates. */
export function computeScanTopology(mesh: ScanMesh, scanToPart: THREE.Matrix4): ScanTopology {
  const positions = mesh.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  const neighbours = new Int32Array(mesh.faceCount * 3).fill(-1);
  const vertexIds = new Map<string, number>();
  const vertexId = (corner: number) => {
    const key = `${positions.getX(corner)},${positions.getY(corner)},${positions.getZ(corner)}`;
    let id = vertexIds.get(key);
    if (id === undefined) {
      id = vertexIds.size;
      vertexIds.set(key, id);
    }
    return id;
  };
  const edges = new Map<string, number>();
  for (let face = 0; face < mesh.faceCount; face += 1) {
    const ids = [vertexId(face * 3), vertexId(face * 3 + 1), vertexId(face * 3 + 2)];
    for (let slot = 0; slot < 3; slot += 1) {
      const a = ids[slot] ?? 0;
      const b = ids[(slot + 1) % 3] ?? 0;
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      const other = edges.get(key);
      if (other === undefined) {
        edges.set(key, face * 3 + slot);
      } else if (other >= 0) {
        neighbours[face * 3 + slot] = Math.floor(other / 3);
        neighbours[other] = face;
        edges.set(key, -1);
      }
    }
  }
  const centroids = new Float32Array(mesh.centroids.length);
  const point = new THREE.Vector3();
  for (let face = 0; face < mesh.faceCount; face += 1) {
    point
      .fromArray(mesh.centroids, face * 3)
      .applyMatrix4(scanToPart)
      .toArray(centroids, face * 3);
  }
  return { neighbours, centroids };
}
