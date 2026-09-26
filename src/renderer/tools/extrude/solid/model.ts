// Rules shared by the solid tools (Extrusion, Drehung, Grundkörper, Körper teilen,
// Kombinieren, Verrundung): which bodies and features a tool may use, and the
// operation / target body rule of ARCHITECTURE.md 4.5. Strings: `tools:extrude.solid.*`.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { BodyOperation } from '@shared/protocol/generated/features-common';

export const OPERATIONS: readonly BodyOperation[] = ['newBody', 'add', 'cut', 'intersect'];

export const ORIGIN_PLANES = ['XY', 'YZ', 'XZ'] as const;
export const ORIGIN_AXES = ['X', 'Y', 'Z'] as const;

export interface BodyOption {
  id: string;
  /** Position in the rebuild order, as the project tree numbers bodies ("Körper 2"). */
  number: number;
}

/** A problem that keeps OK disabled; the value is the i18n key below `tools:extrude.solid`. */
export type InputProblem = 'targetMissing' | 'targetUnknown' | 'targetIsTool' | 'toolsMissing';

type Snapshot = Pick<DocumentSnapshot, 'document' | 'status'>;

function featureIndex(snapshot: Snapshot, id: string | null): number {
  if (id === null) return snapshot.document.features.length;
  const index = snapshot.document.features.findIndex((feature) => feature.id === id);
  return index === -1 ? snapshot.document.features.length : index;
}

/**
 * Bodies a feature may use: the current bodies, numbered like the tree. While a
 * feature is edited, only bodies created by earlier features qualify.
 */
export function availableBodies(snapshot: Snapshot, editTarget: string | null): BodyOption[] {
  const limit = featureIndex(snapshot, editTarget);
  return snapshot.status.bodies
    .map((body, index) => ({ id: body.id, number: index + 1 }))
    .filter((body) => featureIndex(snapshot, body.id) < limit);
}

export function needsTarget(operation: BodyOperation): boolean {
  return operation !== 'newBody';
}

export function targetProblem(
  operation: BodyOperation,
  targetBody: string | null,
  bodies: readonly BodyOption[],
): InputProblem | null {
  if (!needsTarget(operation)) return null;
  if (!targetBody) return 'targetMissing';
  return bodies.some((body) => body.id === targetBody) ? null : 'targetUnknown';
}

/** The body a new add/cut/intersect should use: the most recently created one. */
export function defaultTarget(bodies: readonly BodyOption[]): string | null {
  return bodies.at(-1)?.id ?? null;
}

export function toolsProblem(
  targetBody: string | null,
  tools: readonly string[],
): InputProblem | null {
  if (!targetBody) return 'targetMissing';
  if (tools.length === 0) return 'toolsMissing';
  return tools.includes(targetBody) ? 'targetIsTool' : null;
}

interface FeatureLike {
  id: string;
  type: string;
  params: unknown;
}

function field(params: unknown, key: string): unknown {
  return typeof params === 'object' && params !== null
    ? (params as Record<string, unknown>)[key]
    : undefined;
}

function definitionType(feature: FeatureLike): unknown {
  return field(field(feature.params, 'definition'), 'type');
}

const PLANE_REFERENCES = new Set(['offsetPlane', 'midPlane', 'planeThroughAxis']);
const AXIS_FITS = new Set(['cylinder', 'cone', 'torus']);
const BODY_FITS = new Set(['cylinder', 'cone', 'sphere', 'torus']);

export function isSketch(feature: FeatureLike): boolean {
  return feature.type === 'sketch';
}

export function isPlane(feature: FeatureLike): boolean {
  if (feature.type === 'fit') return field(feature.params, 'kind') === 'plane';
  return feature.type === 'reference' && PLANE_REFERENCES.has(String(definitionType(feature)));
}

export function isAxis(feature: FeatureLike): boolean {
  if (feature.type === 'fit') return AXIS_FITS.has(String(field(feature.params, 'kind')));
  return feature.type === 'reference' && definitionType(feature) === 'axisFromPlanes';
}

/** Fits a primitive body can be made from. */
export function isBodyFit(feature: FeatureLike): boolean {
  return feature.type === 'fit' && BODY_FITS.has(String(field(feature.params, 'kind')));
}

export function isPatch(feature: FeatureLike): boolean {
  return feature.type === 'freeformPatch';
}

/**
 * Features before `editTarget` (or all) that match and evaluated without error,
 * most recent last.
 */
export function usableFeatures(
  snapshot: Snapshot,
  matches: (feature: FeatureLike) => boolean,
  editTarget: string | null,
): string[] {
  const limit = featureIndex(snapshot, editTarget);
  return snapshot.document.features
    .slice(0, limit)
    .filter((feature) => {
      const state = snapshot.status.features[feature.id]?.state;
      return matches(feature) && (state === 'ok' || state === 'warning');
    })
    .map((feature) => feature.id);
}

/** Stored parameters of the edited feature, if it has the expected type. */
export function storedParams<T>(
  snapshot: Snapshot | null,
  editTarget: string | null,
  type: string,
): T | null {
  if (!snapshot || !editTarget) return null;
  const feature = snapshot.document.features.find((item) => item.id === editTarget);
  return feature?.type === type ? (feature.params as T) : null;
}

/** A length a solid tool accepts: finite and at least 1 µm. */
export function isPositiveLength(value: number | null): value is number {
  return value !== null && Number.isFinite(value) && value >= 0.001;
}
