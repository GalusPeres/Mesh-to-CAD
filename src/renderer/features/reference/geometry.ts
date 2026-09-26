// What fit and reference features provide as inputs for other features: a plane, an
// axis or a point, and where it lies. The geometry comes from the feature statistics
// the kernel reports (`pointX/Y/Z`, `directionX/Y/Z`), so the renderer never refits.

import type { Feature } from '@shared/protocol/generated/document-model';
import type { FeatureStatus } from '@shared/protocol/generated/document-results';

export type Vec3 = readonly [number, number, number];
export type GeometryKind = 'plane' | 'axis' | 'point';

export interface Frame {
  point: Vec3;
  /** Plane normal or axis direction (unit). */
  direction: Vec3;
}

export const ORIGIN_PLANES: Readonly<Record<'XY' | 'YZ' | 'XZ', Vec3>> = {
  XY: [0, 0, 1],
  YZ: [1, 0, 0],
  XZ: [0, 1, 0],
};

export const ORIGIN_AXES: Readonly<Record<'X' | 'Y' | 'Z', Vec3>> = {
  X: [1, 0, 0],
  Y: [0, 1, 0],
  Z: [0, 0, 1],
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

/** The kind of geometry a feature offers to others, or null (bodies, sketches, ...). */
export function providedGeometry(feature: Feature): GeometryKind | null {
  const params = record(feature.params);
  if (feature.type === 'fit') {
    if (params.kind === 'plane') return 'plane';
    return params.kind === 'sphere' ? 'point' : 'axis';
  }
  if (feature.type === 'reference') {
    return record(params.definition).type === 'axisFromPlanes' ? 'axis' : 'plane';
  }
  return null;
}

function vector(stats: Record<string, number | null>, name: string): Vec3 | null {
  const values = ['X', 'Y', 'Z'].map((axis) => stats[`${name}${axis}`]);
  if (values.some((value) => typeof value !== 'number')) return null;
  return values as unknown as Vec3;
}

/** Point and direction of an evaluated fit or reference feature. */
export function featureFrame(status: FeatureStatus | undefined): Frame | null {
  if (!status) return null;
  const point = vector(status.stats, 'point');
  const direction = vector(status.stats, 'direction');
  return point && direction ? { point, direction } : null;
}

/** Point and direction of an origin plane or axis, or of a feature (by id). */
export function inputFrame(
  name: string,
  statuses: Readonly<Record<string, FeatureStatus>>,
): Frame | null {
  const origin: Vec3 = [0, 0, 0];
  if (name in ORIGIN_PLANES) return { point: origin, direction: ORIGIN_PLANES[name as 'XY'] };
  if (name in ORIGIN_AXES) return { point: origin, direction: ORIGIN_AXES[name as 'X'] };
  return featureFrame(statuses[name]);
}

/**
 * Features that can serve as a plane or an axis input: evaluated without error and,
 * when a feature is being edited, earlier in the history than that feature.
 */
export function inputFeatures(
  features: readonly Feature[],
  statuses: Readonly<Record<string, FeatureStatus>>,
  kind: GeometryKind,
  before: string | null,
): Feature[] {
  const end = before ? features.findIndex((feature) => feature.id === before) : -1;
  const earlier = end >= 0 ? features.slice(0, end) : features;
  return earlier.filter((feature) => {
    const state = statuses[feature.id]?.state;
    const usable = state === 'ok' || state === 'warning';
    return usable && !feature.suppressed && providedGeometry(feature) === kind;
  });
}

/**
 * In-plane direction of a plane through an axis at 0 degrees (kernel `angle_zero_direction`):
 * X, or Y for axes within 45 degrees of X, made perpendicular to the axis.
 */
export function angleZeroDirection(axis: Vec3): Vec3 {
  const reference: Vec3 = Math.abs(axis[0]) < Math.SQRT1_2 ? [1, 0, 0] : [0, 1, 0];
  const along = reference[0] * axis[0] + reference[1] * axis[1] + reference[2] * axis[2];
  const x = reference[0] - along * axis[0];
  const y = reference[1] - along * axis[1];
  const z = reference[2] - along * axis[2];
  const length = Math.hypot(x, y, z);
  return [x / length, y / length, z / length];
}
