// Closest points on the displayed scan for part-coordinate points: snapping and the
// live deviation colours of tools that edit geometry lying on the scan. Uses the
// scan's BVH (attached with its topology), so it answers only after that exists.

import * as THREE from 'three';
import type { HitPointInfo } from 'three-mesh-bvh';

import type { ScanSurfacePoint, ScanSurfaceQueries, Vec3 } from './api';
import type { ScanMesh } from './scanMesh';

const query = new THREE.Vector3();
const hit: HitPointInfo = { point: new THREE.Vector3(), distance: 0, faceIndex: 0 };
const normal = new THREE.Vector3();
const normalMatrix = new THREE.Matrix3();
const partToScan = new THREE.Matrix4();

/** Signed distance of `query` (scan-local) to the hit: positive outside the material. */
function signedDistance(faceNormals: Float32Array): number {
  const o = hit.faceIndex * 3;
  const dot =
    (query.x - hit.point.x) * (faceNormals[o] ?? 0) +
    (query.y - hit.point.y) * (faceNormals[o + 1] ?? 0) +
    (query.z - hit.point.z) * (faceNormals[o + 2] ?? 0);
  return dot < 0 ? -hit.distance : hit.distance;
}

export function closestScanPoint(
  scan: ScanMesh,
  scanToPart: THREE.Matrix4,
  point: Vec3,
  maxDistance: number,
): ScanSurfacePoint | null {
  const topology = scan.topology;
  if (!topology) return null;
  partToScan.copy(scanToPart).invert();
  query.set(point[0], point[1], point[2]).applyMatrix4(partToScan);
  if (!topology.bvh.closestPointToPoint(query, hit, 0, maxDistance)) return null;
  const distance = signedDistance(topology.faceNormals);
  const o = hit.faceIndex * 3;
  normal
    .set(
      topology.faceNormals[o] ?? 0,
      topology.faceNormals[o + 1] ?? 0,
      topology.faceNormals[o + 2] ?? 1,
    )
    .applyMatrix3(normalMatrix.getNormalMatrix(scanToPart))
    .normalize();
  const onScan = hit.point.clone().applyMatrix4(scanToPart);
  return {
    point: [onScan.x, onScan.y, onScan.z],
    normal: [normal.x, normal.y, normal.z],
    distance,
  };
}

export function scanDistances(
  scan: ScanMesh,
  scanToPart: THREE.Matrix4,
  points: Float32Array,
  out: Float32Array,
  maxDistance: number,
  indices?: Uint32Array,
): boolean {
  const topology = scan.topology;
  if (!topology) return false;
  partToScan.copy(scanToPart).invert();
  const { bvh, faceNormals } = topology;
  const measure = (i: number) => {
    const o = i * 3;
    query.set(points[o] ?? 0, points[o + 1] ?? 0, points[o + 2] ?? 0).applyMatrix4(partToScan);
    out[i] = bvh.closestPointToPoint(query, hit, 0, maxDistance)
      ? signedDistance(faceNormals)
      : Number.NaN;
  };
  if (indices) for (const i of indices) measure(i);
  else for (let i = 0; i < points.length / 3; i += 1) measure(i);
  return true;
}

/** The viewport's scan-surface queries for the scan shown now (none before it loads). */
export function createScanSurfaceQueries(
  scan: () => ScanMesh | null,
  scanToPart: THREE.Matrix4,
): ScanSurfaceQueries {
  return {
    closest: (point, maxDistance) => {
      const current = scan();
      return current ? closestScanPoint(current, scanToPart, point, maxDistance) : null;
    },
    distances: (points, out, maxDistance, indices) => {
      const current = scan();
      return !!current && scanDistances(current, scanToPart, points, out, maxDistance, indices);
    },
  };
}
