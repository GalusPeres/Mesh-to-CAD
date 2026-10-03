// Edge references of the fillet tool (ARCHITECTURE.md 4.6). A picked edge becomes the
// pair of face tags on both sides plus a point on it: the body edge payload names the
// two B-Rep faces of every segment (`faces`), and `status.bodies[].faceTags` gives
// their tags. The same rule resolves stored references back to displayed edges.

import type { EdgeRef } from '@shared/protocol/generated/feature-fillet';
import type { Vec3 } from '@shared/protocol/generated/geometry';

/** A point as picking returns it. */
type Point = readonly [number, number, number];

export interface EdgePayload {
  /** (s, 2, 3) line segments. */
  segments: Float32Array;
  /** B-Rep edge index of each segment. */
  ids: Uint32Array;
  /** (s, 2) B-Rep faces on both sides of each segment's edge. */
  faces: Uint32Array | null;
}

interface Nearest {
  edge: number;
  distance: number;
}

function segmentDistance(payload: EdgePayload, segment: number, point: Point): number {
  const s = payload.segments;
  const base = segment * 6;
  const a: Vec3 = [s[base]!, s[base + 1]!, s[base + 2]!];
  const d: Vec3 = [s[base + 3]! - a[0], s[base + 4]! - a[1], s[base + 5]! - a[2]];
  const p: Vec3 = [point[0] - a[0], point[1] - a[1], point[2] - a[2]];
  const lengthSquared = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
  const along =
    lengthSquared > 0
      ? Math.min(1, Math.max(0, (p[0] * d[0] + p[1] * d[1] + p[2] * d[2]) / lengthSquared))
      : 0;
  const x = p[0] - along * d[0];
  const y = p[1] - along * d[1];
  const z = p[2] - along * d[2];
  return Math.sqrt(x * x + y * y + z * z);
}

/** The edge whose polyline passes closest to `point`, within `tolerance`. */
export function nearestEdge(
  payload: EdgePayload,
  point: Point,
  tolerance: number,
  accept: (edge: number) => boolean = () => true,
): Nearest | null {
  let best: Nearest | null = null;
  for (let segment = 0; segment < payload.ids.length; segment++) {
    const edge = payload.ids[segment]!;
    if (!accept(edge)) continue;
    const distance = segmentDistance(payload, segment, point);
    if (distance <= tolerance && (!best || distance < best.distance)) best = { edge, distance };
  }
  return best;
}

/** Face tags on both sides of an edge, or null when the payload does not know them. */
export function edgeFaceTags(
  payload: EdgePayload,
  faceTags: readonly string[],
  edge: number,
): [string, string] | null {
  if (!payload.faces) return null;
  const segment = payload.ids.indexOf(edge);
  if (segment < 0) return null;
  const first = faceTags[payload.faces[segment * 2]!];
  const second = faceTags[payload.faces[segment * 2 + 1]!];
  return first !== undefined && second !== undefined ? [first, second] : null;
}

export function edgeRef(
  payload: EdgePayload,
  faceTags: readonly string[],
  edge: number,
  point: Point,
): EdgeRef | null {
  const faces = edgeFaceTags(payload, faceTags, edge);
  return faces ? { faces, point: [point[0], point[1], point[2]] } : null;
}

function samePair(a: readonly [string, string], b: readonly [string, string]): boolean {
  return (a[0] === b[0] && a[1] === b[1]) || (a[0] === b[1] && a[1] === b[0]);
}

/**
 * The displayed edge a stored reference stands for: among the edges between faces with
 * the two tags, the one closest to the reference point (as the kernel resolves it).
 */
export function edgeForRef(
  payload: EdgePayload,
  faceTags: readonly string[],
  ref: EdgeRef,
): number | null {
  const candidates = new Set<number>();
  for (let segment = 0; segment < payload.ids.length; segment++) {
    const edge = payload.ids[segment]!;
    if (candidates.has(edge)) continue;
    const tags = edgeFaceTags(payload, faceTags, edge);
    if (tags && samePair(tags, ref.faces)) candidates.add(edge);
  }
  if (candidates.size <= 1) return candidates.values().next().value ?? null;
  return nearestEdge(payload, ref.point, Infinity, (edge) => candidates.has(edge))?.edge ?? null;
}

/** All segments of the given edges, 6 numbers per segment. */
export function edgeSegments(payload: EdgePayload, edges: ReadonlySet<number>): Float32Array {
  const parts: number[] = [];
  for (let segment = 0; segment < payload.ids.length; segment++) {
    if (!edges.has(payload.ids[segment]!)) continue;
    for (let k = 0; k < 6; k++) parts.push(payload.segments[segment * 6 + k]!);
  }
  return new Float32Array(parts);
}

/** Faces the edited feature created itself cannot be the input of the same feature. */
export function touchesFeature(ref: EdgeRef, featureId: string | null): boolean {
  return featureId !== null && ref.faces.some((tag) => tag.startsWith(`${featureId}:`));
}

/** Pick tolerance: a small share of the body size, at least 0.02 mm. */
export function pickTolerance(payload: EdgePayload): number {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const s = payload.segments;
  for (let i = 0; i < s.length; i += 3) {
    for (let axis = 0; axis < 3; axis++) {
      min[axis] = Math.min(min[axis]!, s[i + axis]!);
      max[axis] = Math.max(max[axis]!, s[i + axis]!);
    }
  }
  const diagonal = Math.hypot(max[0]! - min[0]!, max[1]! - min[1]!, max[2]! - min[2]!);
  return Number.isFinite(diagonal) ? Math.max(0.02, diagonal * 0.002) : 0.02;
}
