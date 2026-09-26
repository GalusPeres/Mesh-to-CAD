// Scan-face queries on the UI thread: the brush circle (BVH candidates, then the
// visibility test of scanVisibility.ts), the nearest face under a ray, and
// centroids in part coordinates for scanTopology().

import * as THREE from 'three';
import { CONTAINED, INTERSECTED, NOT_INTERSECTED } from 'three-mesh-bvh';

import type { FaceIdImage } from './faceIds';
import type { ScanMesh } from './scanMesh';
import {
  type PickView,
  type ScreenPosition,
  isClipped,
  isFaceVisible,
  projectToScreen,
} from './scanVisibility';

const corner = new THREE.Vector3();
const screen: ScreenPosition = { x: 0, y: 0 };

/** Screen rectangle of a box, or null when part of it lies behind the camera. */
function screenRect(view: PickView, box: THREE.Box3): [number, number, number, number] | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < 8; i += 1) {
    corner.set(
      i & 1 ? box.max.x : box.min.x,
      i & 2 ? box.max.y : box.min.y,
      i & 4 ? box.max.z : box.min.z,
    );
    if (!projectToScreen(view, corner.x, corner.y, corner.z, screen)) return null;
    minX = Math.min(minX, screen.x);
    maxX = Math.max(maxX, screen.x);
    minY = Math.min(minY, screen.y);
    maxY = Math.max(maxY, screen.y);
  }
  return [minX, minY, maxX, maxY];
}

/**
 * Faces whose centroid projects within `radius` CSS pixels of `at`; with an id
 * image only the visible ones. Hidden and clipped faces never count.
 */
export function pickFacesInCircle(
  scan: ScanMesh,
  view: PickView,
  at: { x: number; y: number },
  radius: number,
  image: FaceIdImage | null,
): Uint32Array {
  const topology = scan.topology;
  if (!topology) return new Uint32Array();
  const { bvh, centroids, faceNormals } = topology;
  const radiusSquared = radius * radius;
  const picked: number[] = [];
  const position: ScreenPosition = { x: 0, y: 0 };
  bvh.shapecast({
    intersectsBounds: (box) => {
      const rect = screenRect(view, box);
      if (!rect) return INTERSECTED;
      const [minX, minY, maxX, maxY] = rect;
      const dx = Math.max(minX - at.x, 0, at.x - maxX);
      const dy = Math.max(minY - at.y, 0, at.y - maxY);
      if (dx * dx + dy * dy > radiusSquared) return NOT_INTERSECTED;
      const far = Math.max(
        Math.hypot(minX - at.x, minY - at.y),
        Math.hypot(maxX - at.x, minY - at.y),
        Math.hypot(minX - at.x, maxY - at.y),
        Math.hypot(maxX - at.x, maxY - at.y),
      );
      return far <= radius ? CONTAINED : INTERSECTED;
    },
    intersectsRange: (offset, count) => {
      for (let i = offset; i < offset + count; i += 1) {
        const face = bvh.resolveTriangleIndex(i);
        if (scan.isHidden(face) || isClipped(view, centroids, face)) continue;
        const o = face * 3;
        const inView = projectToScreen(
          view,
          centroids[o] ?? 0,
          centroids[o + 1] ?? 0,
          centroids[o + 2] ?? 0,
          position,
        );
        if (!inView) continue;
        const dx = position.x - at.x;
        const dy = position.y - at.y;
        if (dx * dx + dy * dy > radiusSquared) continue;
        if (
          image &&
          !isFaceVisible(face, position.x, position.y, centroids, faceNormals, view, image)
        )
          continue;
        picked.push(face);
      }
      return false;
    },
  });
  return Uint32Array.from(picked);
}

export interface ScanRayHit {
  face: number;
  /** Scan-local hit point. */
  point: THREE.Vector3;
  distance: number;
}

/**
 * The nearest face a scan-local ray hits that is neither hidden nor cut away by
 * the section plane (scan-local, the side the normal points to is removed).
 */
export function raycastScan(
  scan: ScanMesh,
  ray: THREE.Ray,
  clip: THREE.Plane | null,
): ScanRayHit | null {
  const bvh = scan.topology?.bvh;
  if (!bvh) return null;
  const hits = bvh.raycast(ray, THREE.DoubleSide);
  hits.sort((a, b) => a.distance - b.distance);
  for (const hit of hits) {
    const face = hit.faceIndex ?? -1;
    if (face < 0 || scan.isHidden(face)) continue;
    if (clip && clip.distanceToPoint(hit.point) > 0) continue;
    return { face, point: hit.point.clone(), distance: hit.distance };
  }
  return null;
}

/** Face centroids moved from scan-local to part coordinates. */
export function partCentroids(centroids: Float32Array, scanToPart: THREE.Matrix4): Float32Array {
  const result = new Float32Array(centroids.length);
  const e = scanToPart.elements;
  for (let o = 0; o < centroids.length; o += 3) {
    const x = centroids[o] ?? 0;
    const y = centroids[o + 1] ?? 0;
    const z = centroids[o + 2] ?? 0;
    result[o] = e[0] * x + e[4] * y + e[8] * z + e[12];
    result[o + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
    result[o + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
  }
  return result;
}
